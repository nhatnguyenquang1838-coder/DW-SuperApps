-- DWO v2 / GWC v2 native observation contract finalization.
-- Phase A is zero-downtime compatible: install the new source-bound RPC while
-- retaining a safe legacy 2-arg wrapper until the Edge Function is upgraded.

SELECT pg_advisory_xact_lock(hashtextextended('dwo:gwc-observation-v2:migration', 0));

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'runs','run_gates','run_nodes','projection_events',
    'observation_source_bindings','observation_machine_keys',
    'observation_events_raw','observation_ingest_cursors'
  ]
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'DWO_OBSERVATION_PREREQUISITE_MISSING:%', t;
    END IF;
  END LOOP;
END
$$;

ALTER TABLE public.observation_source_bindings
  ADD COLUMN IF NOT EXISTS sha_policy text NOT NULL DEFAULT 'EXACT';

ALTER TABLE public.observation_source_bindings
  ALTER COLUMN source_sha DROP NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.observation_source_bindings'::regclass
      AND conname = 'observation_source_bindings_sha_policy_check'
  ) THEN
    ALTER TABLE public.observation_source_bindings
      ADD CONSTRAINT observation_source_bindings_sha_policy_check
      CHECK (
        (sha_policy = 'EXACT' AND source_sha IS NOT NULL AND source_sha ~ '^[0-9a-f]{40}$')
        OR (sha_policy = 'ANY_SIGNED' AND source_sha IS NULL)
      );
  END IF;
END
$$;

ALTER TABLE public.observation_events_raw
  ADD COLUMN IF NOT EXISTS accepted_source_id text;

CREATE INDEX IF NOT EXISTS idx_observation_raw_accepted_source
  ON public.observation_events_raw (accepted_source_id)
  WHERE accepted_source_id IS NOT NULL;

WITH candidates AS (
  SELECT r.id, min(b.source_id) AS source_id, count(*) AS matches
  FROM public.observation_events_raw r
  JOIN public.observation_source_bindings b
    ON b.source_system = r.source_system
   AND b.source_repository = r.source_repository
   AND b.source_schema = r.source_schema
   AND b.source_sha = r.source_sha
  WHERE r.accepted_source_id IS NULL
  GROUP BY r.id
)
UPDATE public.observation_events_raw r
SET accepted_source_id = c.source_id
FROM candidates c
WHERE r.id = c.id
  AND c.matches = 1;

UPDATE public.observation_source_bindings
SET sha_policy = 'ANY_SIGNED',
    source_sha = NULL,
    updated_at = now()
WHERE source_id = 'gwc-main';

UPDATE public.observation_source_bindings
SET sha_policy = 'EXACT'
WHERE source_id <> 'gwc-main'
  AND source_sha IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_observation_source_binding_lookup
  ON public.observation_source_bindings
     (source_id, source_system, source_repository, source_schema, enabled);

CREATE OR REPLACE FUNCTION public._materialize_gwc_observation_read_model_v2(
  p_event jsonb,
  p_accepted_source_id text
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_run_id text := p_event->>'run_id';
  v_event_id text := p_event->>'event_id';
  v_sequence bigint := (p_event->>'sequence')::bigint;
  v_occurred_at timestamptz := (p_event->>'occurred_at')::timestamptz;
  v_source_sha text := p_event #>> '{source,sha}';
  v_source_schema text := p_event->>'schema_id';
  v_gate text := p_event #>> '{runtime,gate}';
  v_runtime_state text := p_event #>> '{runtime,state}';
  v_node_source text := p_event #>> '{runtime,node_id}';
  v_from_gate text := p_event #>> '{payload,from_gate}';
  v_gate_id text;
  v_node_id text;
  v_source_refs text[];
BEGIN
  IF v_run_id IS NULL OR v_event_id IS NULL THEN
    RAISE EXCEPTION 'OBSERVATION_READ_MODEL_IDENTITY_MISSING' USING ERRCODE='P0001';
  END IF;

  IF v_from_gate IS NULL OR btrim(v_from_gate) = '' THEN
    SELECT r.gate
      INTO v_from_gate
    FROM public.observation_events_raw r
    WHERE r.source_system = 'gwc'
      AND r.run_id = v_run_id
      AND r.source_sequence < v_sequence
      AND r.gate IS NOT NULL
    ORDER BY r.source_sequence DESC, r.id DESC
    LIMIT 1;
  END IF;

  v_gate_id := CASE
    WHEN v_gate IS NULL OR btrim(v_gate) = '' THEN NULL
    ELSE v_run_id || '::' || v_gate
  END;

  v_node_id := CASE
    WHEN v_node_source IS NULL OR btrim(v_node_source) = '' THEN NULL
    ELSE v_run_id || '::node::' || v_node_source
  END;

  v_source_refs := ARRAY(
    SELECT DISTINCT x
    FROM unnest(
      ARRAY[v_event_id] ||
      ARRAY(
        SELECT jsonb_array_elements_text(
          CASE
            WHEN jsonb_typeof(COALESCE(p_event->'evidence_refs','[]'::jsonb)) = 'array'
              THEN COALESCE(p_event->'evidence_refs','[]'::jsonb)
            ELSE '[]'::jsonb
          END
        )
      )
    ) AS x
    WHERE x IS NOT NULL AND btrim(x) <> ''
  );

  INSERT INTO public.runs (
    run_id, run_kind, source_system, head_sha, authority_ref,
    started_at, completed_at, source_refs, payload
  ) VALUES (
    v_run_id, 'observed_real', 'gwc', v_source_sha, p_event->>'authority_ref',
    v_occurred_at,
    CASE WHEN v_gate = 'UR.G6' AND v_runtime_state = 'PASSED' THEN v_occurred_at ELSE NULL END,
    v_source_refs,
    jsonb_build_object(
      'runtime_epoch', p_event #>> '{runtime,epoch}',
      'lifecycle_profile', p_event #> '{runtime,profile}',
      'observation_contract', v_source_schema,
      'accepted_source_id', p_accepted_source_id,
      'last_source_sequence', v_sequence,
      'last_typed_next', p_event #>> '{runtime,typed_next}'
    )
  )
  ON CONFLICT (run_id) DO UPDATE SET
    head_sha = EXCLUDED.head_sha,
    authority_ref = COALESCE(EXCLUDED.authority_ref, runs.authority_ref),
    started_at = LEAST(COALESCE(runs.started_at, EXCLUDED.started_at), EXCLUDED.started_at),
    completed_at = COALESCE(EXCLUDED.completed_at, runs.completed_at),
    source_refs = ARRAY(
      SELECT DISTINCT x
      FROM unnest(COALESCE(runs.source_refs,'{}'::text[]) || EXCLUDED.source_refs) AS x
      WHERE x IS NOT NULL AND btrim(x) <> ''
    ),
    payload = runs.payload || EXCLUDED.payload;

  IF v_gate_id IS NOT NULL THEN
    IF v_from_gate IS NOT NULL
       AND btrim(v_from_gate) <> ''
       AND v_from_gate <> v_gate THEN
      UPDATE public.run_gates
      SET state = 'PASSED',
          summary = 'Transitioned to ' || v_gate
      WHERE gate_id = v_run_id || '::' || v_from_gate
        AND run_id = v_run_id;

      UPDATE public.run_nodes
      SET state = 'PASSED'
      WHERE gate_id = v_run_id || '::' || v_from_gate
        AND run_id = v_run_id;
    END IF;

    INSERT INTO public.run_gates (
      gate_id, run_id, gate_label, boundary, authority_ref, state, summary,
      node_count, artifact_count, source_refs
    ) VALUES (
      v_gate_id, v_run_id, v_gate, 'GWC_UNIVERSAL_V2',
      p_event->>'authority_ref',
      COALESCE(NULLIF(v_runtime_state,''), NULLIF(p_event->>'outcome',''), 'UNKNOWN'),
      COALESCE(p_event->>'event_type','RUN_STATE_CHANGED') || ' / ' ||
        COALESCE(NULLIF(p_event->>'outcome',''),'UNKNOWN'),
      0,
      CASE
        WHEN jsonb_typeof(COALESCE(p_event->'evidence_refs','[]'::jsonb)) = 'array'
          THEN jsonb_array_length(COALESCE(p_event->'evidence_refs','[]'::jsonb))
        ELSE 0
      END,
      v_source_refs
    )
    ON CONFLICT (gate_id) DO UPDATE SET
      state = EXCLUDED.state,
      authority_ref = COALESCE(EXCLUDED.authority_ref, run_gates.authority_ref),
      summary = EXCLUDED.summary,
      artifact_count = GREATEST(COALESCE(run_gates.artifact_count,0), COALESCE(EXCLUDED.artifact_count,0)),
      source_refs = ARRAY(
        SELECT DISTINCT x
        FROM unnest(COALESCE(run_gates.source_refs,'{}'::text[]) || EXCLUDED.source_refs) AS x
        WHERE x IS NOT NULL AND btrim(x) <> ''
      );

    IF v_node_id IS NOT NULL THEN
      INSERT INTO public.run_nodes (
        node_id, run_id, gate_id, family, boundary, state, label, source_refs
      ) VALUES (
        v_node_id, v_run_id, v_gate_id,
        'GWC_UNIVERSAL_V2', 'OBSERVED_RUNTIME',
        COALESCE(NULLIF(v_runtime_state,''), NULLIF(p_event->>'outcome',''), 'UNKNOWN'),
        v_node_source, v_source_refs
      )
      ON CONFLICT (node_id) DO UPDATE SET
        gate_id = EXCLUDED.gate_id,
        state = EXCLUDED.state,
        label = EXCLUDED.label,
        source_refs = ARRAY(
          SELECT DISTINCT x
          FROM unnest(COALESCE(run_nodes.source_refs,'{}'::text[]) || EXCLUDED.source_refs) AS x
          WHERE x IS NOT NULL AND btrim(x) <> ''
        );
    END IF;

    UPDATE public.run_gates g
    SET node_count = (
      SELECT count(*)::int
      FROM public.run_nodes n
      WHERE n.run_id = v_run_id
        AND n.gate_id = v_gate_id
    )
    WHERE g.gate_id = v_gate_id;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public._materialize_gwc_observation_read_model_v2(jsonb,text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public._materialize_gwc_observation_read_model_v2(jsonb,text)
  TO service_role;

CREATE OR REPLACE FUNCTION public.ingest_observation_event_v2(
  p_source_id text,
  p_event jsonb,
  p_event_payload_digest text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_source_system text;
  v_source_event_id text;
  v_run_id text;
  v_sequence bigint;
  v_existing public.observation_events_raw%ROWTYPE;
  v_cursor public.observation_ingest_cursors%ROWTYPE;
  v_raw_id bigint;
  v_projection_ordinal bigint;
  v_source_sha text;
  v_source_repository text;
  v_source_schema text;
  v_occurred_at timestamptz;
BEGIN
  IF p_event IS NULL
     OR p_event->>'schema_id' <> 'gwc.observation-event/v2'
     OR p_event->>'schema_version' <> '2'
     OR p_event #>> '{source,system}' <> 'gwc' THEN
    RAISE EXCEPTION 'SCHEMA_UNSUPPORTED' USING ERRCODE='P0001';
  END IF;

  IF p_source_id IS NULL OR btrim(p_source_id) = ''
     OR p_event->>'event_id' IS NULL
     OR p_event->>'run_id' IS NULL
     OR p_event->>'sequence' !~ '^[0-9]+$'
     OR p_event #>> '{source,sha}' !~ '^[0-9a-f]{40}$'
     OR p_event->>'source_digest' !~ '^sha256:[0-9a-f]{64}$'
     OR p_event_payload_digest !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'OBSERVATION_EVENT_INVALID' USING ERRCODE='P0001';
  END IF;

  v_source_system := p_event #>> '{source,system}';
  v_source_event_id := p_event->>'event_id';
  v_run_id := p_event->>'run_id';
  v_sequence := (p_event->>'sequence')::bigint;
  v_source_sha := p_event #>> '{source,sha}';
  v_source_repository := p_event #>> '{source,repository}';
  v_source_schema := p_event->>'schema_id';

  BEGIN
    v_occurred_at := (p_event->>'occurred_at')::timestamptz;
  EXCEPTION WHEN others THEN
    RAISE EXCEPTION 'OBSERVATION_EVENT_INVALID' USING ERRCODE='P0001';
  END;

  IF NOT EXISTS (
    SELECT 1
    FROM public.observation_source_bindings b
    WHERE b.enabled
      AND b.source_id = p_source_id
      AND b.source_system = v_source_system
      AND b.source_repository = v_source_repository
      AND b.source_schema = v_source_schema
      AND (
        (b.sha_policy = 'EXACT' AND b.source_sha = v_source_sha)
        OR (b.sha_policy = 'ANY_SIGNED' AND b.source_sha IS NULL)
      )
  ) THEN
    RAISE EXCEPTION 'SOURCE_BINDING_MISMATCH' USING ERRCODE='P0001';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(v_source_system || ':' || v_run_id, 0)
  );

  SELECT *
    INTO v_existing
  FROM public.observation_events_raw
  WHERE source_system = v_source_system
    AND source_event_id = v_source_event_id;

  IF FOUND THEN
    IF v_existing.event_payload_digest <> p_event_payload_digest THEN
      RAISE EXCEPTION 'EVENT_ID_DIGEST_CONFLICT' USING ERRCODE='P0001';
    END IF;
    IF v_existing.accepted_source_id IS NOT NULL
       AND v_existing.accepted_source_id <> p_source_id THEN
      RAISE EXCEPTION 'EVENT_SOURCE_ID_CONFLICT' USING ERRCODE='P0001';
    END IF;

    PERFORM public._materialize_gwc_observation_read_model_v2(
      p_event, COALESCE(v_existing.accepted_source_id, p_source_id)
    );

    UPDATE public.projection_events p
    SET raw_event_id = COALESCE(p.raw_event_id, v_existing.id),
        runtime_epoch = COALESCE(p.runtime_epoch, p_event #>> '{runtime,epoch}'),
        lifecycle_profile = COALESCE(p.lifecycle_profile, p_event #> '{runtime,profile}'),
        runtime_state = COALESCE(p.runtime_state, p_event #>> '{runtime,state}'),
        typed_next = COALESCE(p.typed_next, p_event #>> '{runtime,typed_next}'),
        source_sha = COALESCE(p.source_sha, v_source_sha)
    WHERE p.run_id = v_run_id
      AND p.source_system = v_source_system
      AND p.source_event_id = v_source_event_id;

    IF NOT FOUND THEN
      INSERT INTO public.projection_events (
        run_id, source_system, source_event_id, sequence, event_type, occurred_at,
        gate, node_id, actor, outcome, before, after, evidence_refs, authority_ref,
        source_digest, read_only_projection, raw_event_id, runtime_epoch,
        lifecycle_profile, runtime_state, typed_next, source_sha
      ) VALUES (
        v_run_id, v_source_system, v_source_event_id, v_sequence,
        p_event->>'event_type', v_occurred_at,
        p_event #>> '{runtime,gate}', p_event #>> '{runtime,node_id}',
        p_event->'actor', p_event->>'outcome', NULL, NULL,
        COALESCE(p_event->'evidence_refs','[]'::jsonb),
        p_event->>'authority_ref', p_event->>'source_digest', TRUE,
        v_existing.id, p_event #>> '{runtime,epoch}',
        p_event #> '{runtime,profile}', p_event #>> '{runtime,state}',
        p_event #>> '{runtime,typed_next}', v_source_sha
      )
      RETURNING projection_ordinal INTO v_projection_ordinal;
    ELSE
      SELECT projection_ordinal
        INTO v_projection_ordinal
      FROM public.projection_events
      WHERE run_id = v_run_id
        AND source_system = v_source_system
        AND source_event_id = v_source_event_id;
    END IF;

    UPDATE public.observation_events_raw
    SET projection_status = 'COMMITTED',
        accepted_source_id = COALESCE(accepted_source_id, p_source_id)
    WHERE id = v_existing.id;

    RETURN jsonb_build_object(
      'status','COMMITTED',
      'raw_event_id',v_existing.id,
      'projection_ordinal',v_projection_ordinal,
      'event_id',v_source_event_id,
      'payload_digest',p_event_payload_digest,
      'idempotent_replay',true
    );
  END IF;

  SELECT *
    INTO v_cursor
  FROM public.observation_ingest_cursors
  WHERE source_system = v_source_system
    AND run_id = v_run_id
  FOR UPDATE;

  IF FOUND THEN
    IF v_cursor.gap_state <> 'NONE'
       OR v_sequence <> v_cursor.last_sequence + 1 THEN
      RAISE EXCEPTION 'SOURCE_SEQUENCE_GAP' USING ERRCODE='P0001';
    END IF;
  END IF;

  INSERT INTO public.observation_events_raw (
    source_system, source_schema, source_event_id, run_id, source_sequence,
    event_type, occurred_at, source_repository, source_sha, runtime_epoch,
    lifecycle_profile, gate, runtime_state, node_id, typed_next, outcome, actor,
    authority_ref, evidence_refs, source_digest, event_payload_digest, envelope,
    accepted_source_id
  ) VALUES (
    v_source_system, v_source_schema, v_source_event_id, v_run_id, v_sequence,
    p_event->>'event_type', v_occurred_at, v_source_repository, v_source_sha,
    p_event #>> '{runtime,epoch}', p_event #> '{runtime,profile}',
    p_event #>> '{runtime,gate}', p_event #>> '{runtime,state}',
    p_event #>> '{runtime,node_id}', p_event #>> '{runtime,typed_next}',
    p_event->>'outcome', p_event->'actor', p_event->>'authority_ref',
    COALESCE(p_event->'evidence_refs','[]'::jsonb),
    p_event->>'source_digest', p_event_payload_digest, p_event, p_source_id
  )
  RETURNING id INTO v_raw_id;

  PERFORM public._materialize_gwc_observation_read_model_v2(p_event, p_source_id);

  INSERT INTO public.projection_events (
    run_id, source_system, source_event_id, sequence, event_type, occurred_at,
    gate, node_id, actor, outcome, before, after, evidence_refs, authority_ref,
    source_digest, read_only_projection, raw_event_id, runtime_epoch,
    lifecycle_profile, runtime_state, typed_next, source_sha
  ) VALUES (
    v_run_id, v_source_system, v_source_event_id, v_sequence,
    p_event->>'event_type', v_occurred_at,
    p_event #>> '{runtime,gate}', p_event #>> '{runtime,node_id}',
    p_event->'actor', p_event->>'outcome', NULL, NULL,
    COALESCE(p_event->'evidence_refs','[]'::jsonb),
    p_event->>'authority_ref', p_event->>'source_digest', TRUE,
    v_raw_id, p_event #>> '{runtime,epoch}', p_event #> '{runtime,profile}',
    p_event #>> '{runtime,state}', p_event #>> '{runtime,typed_next}', v_source_sha
  )
  RETURNING projection_ordinal INTO v_projection_ordinal;

  INSERT INTO public.observation_ingest_cursors (
    source_system, run_id, last_sequence, last_event_id,
    last_source_digest, last_event_payload_digest, gap_state
  ) VALUES (
    v_source_system, v_run_id, v_sequence, v_source_event_id,
    p_event->>'source_digest', p_event_payload_digest, 'NONE'
  )
  ON CONFLICT (source_system, run_id) DO UPDATE SET
    last_sequence = EXCLUDED.last_sequence,
    last_event_id = EXCLUDED.last_event_id,
    last_source_digest = EXCLUDED.last_source_digest,
    last_event_payload_digest = EXCLUDED.last_event_payload_digest,
    gap_state = 'NONE',
    updated_at = now();

  UPDATE public.observation_events_raw
  SET projection_status = 'COMMITTED'
  WHERE id = v_raw_id;

  RETURN jsonb_build_object(
    'status','COMMITTED',
    'raw_event_id',v_raw_id,
    'projection_ordinal',v_projection_ordinal,
    'event_id',v_source_event_id,
    'payload_digest',p_event_payload_digest,
    'idempotent_replay',false
  );
END;
$$;

REVOKE ALL ON FUNCTION public.ingest_observation_event_v2(text,jsonb,text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_observation_event_v2(text,jsonb,text)
  TO service_role;

CREATE OR REPLACE FUNCTION public.ingest_observation_event_v2(
  p_event jsonb,
  p_event_payload_digest text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_source_id text;
  v_exact_count int;
  v_any_count int;
BEGIN
  SELECT count(*), min(source_id)
    INTO v_exact_count, v_source_id
  FROM public.observation_source_bindings
  WHERE enabled
    AND source_system = p_event #>> '{source,system}'
    AND source_repository = p_event #>> '{source,repository}'
    AND source_schema = p_event->>'schema_id'
    AND sha_policy = 'EXACT'
    AND source_sha = p_event #>> '{source,sha}';

  IF v_exact_count = 1 THEN
    RETURN public.ingest_observation_event_v2(
      v_source_id, p_event, p_event_payload_digest
    );
  ELSIF v_exact_count > 1 THEN
    RAISE EXCEPTION 'SOURCE_BINDING_AMBIGUOUS' USING ERRCODE='P0001';
  END IF;

  SELECT count(*), min(source_id)
    INTO v_any_count, v_source_id
  FROM public.observation_source_bindings
  WHERE enabled
    AND source_system = p_event #>> '{source,system}'
    AND source_repository = p_event #>> '{source,repository}'
    AND source_schema = p_event->>'schema_id'
    AND sha_policy = 'ANY_SIGNED'
    AND source_sha IS NULL;

  IF v_any_count <> 1 THEN
    RAISE EXCEPTION 'SOURCE_ID_REQUIRED' USING ERRCODE='P0001';
  END IF;

  RETURN public.ingest_observation_event_v2(
    v_source_id, p_event, p_event_payload_digest
  );
END;
$$;

REVOKE ALL ON FUNCTION public.ingest_observation_event_v2(jsonb,text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_observation_event_v2(jsonb,text)
  TO service_role;

UPDATE public.projection_events p
SET raw_event_id = COALESCE(p.raw_event_id, r.id),
    runtime_epoch = COALESCE(p.runtime_epoch, r.runtime_epoch),
    lifecycle_profile = COALESCE(p.lifecycle_profile, r.lifecycle_profile),
    runtime_state = COALESCE(p.runtime_state, r.runtime_state),
    typed_next = COALESCE(p.typed_next, r.typed_next),
    source_sha = COALESCE(p.source_sha, r.source_sha)
FROM public.observation_events_raw r
WHERE p.run_id = r.run_id
  AND p.source_system = r.source_system
  AND p.source_event_id = r.source_event_id;

INSERT INTO public.projection_events (
  run_id, source_system, source_event_id, sequence, event_type, occurred_at,
  gate, node_id, actor, outcome, before, after, evidence_refs, authority_ref,
  source_digest, read_only_projection, raw_event_id, runtime_epoch,
  lifecycle_profile, runtime_state, typed_next, source_sha
)
SELECT
  r.run_id, r.source_system, r.source_event_id, r.source_sequence::int,
  r.event_type, r.occurred_at, r.gate, r.node_id, r.actor, r.outcome,
  NULL, NULL, r.evidence_refs, r.authority_ref, r.source_digest, TRUE,
  r.id, r.runtime_epoch, r.lifecycle_profile, r.runtime_state, r.typed_next,
  r.source_sha
FROM public.observation_events_raw r
WHERE NOT EXISTS (
  SELECT 1
  FROM public.projection_events p
  WHERE p.run_id = r.run_id
    AND p.source_system = r.source_system
    AND p.source_event_id = r.source_event_id
);

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT envelope, accepted_source_id
    FROM public.observation_events_raw
    WHERE source_system = 'gwc'
      AND source_schema = 'gwc.observation-event/v2'
    ORDER BY run_id, source_sequence, id
  LOOP
    PERFORM public._materialize_gwc_observation_read_model_v2(
      r.envelope, r.accepted_source_id
    );
  END LOOP;
END
$$;

WITH stats AS (
  SELECT
    source_system,
    run_id,
    min(source_sequence) AS min_seq,
    max(source_sequence) AS max_seq,
    count(*) AS cnt
  FROM public.observation_events_raw
  GROUP BY source_system, run_id
),
latest AS (
  SELECT DISTINCT ON (r.source_system, r.run_id)
    r.source_system, r.run_id, r.source_sequence,
    r.source_event_id, r.source_digest, r.event_payload_digest
  FROM public.observation_events_raw r
  ORDER BY r.source_system, r.run_id, r.source_sequence DESC, r.id DESC
)
INSERT INTO public.observation_ingest_cursors (
  source_system, run_id, last_sequence, last_event_id,
  last_source_digest, last_event_payload_digest, gap_state
)
SELECT
  l.source_system, l.run_id, l.source_sequence, l.source_event_id,
  l.source_digest, l.event_payload_digest,
  CASE
    WHEN s.cnt = (s.max_seq - s.min_seq + 1) THEN 'NONE'
    ELSE 'GAP'
  END
FROM latest l
JOIN stats s USING (source_system, run_id)
ON CONFLICT (source_system, run_id) DO UPDATE SET
  last_sequence = EXCLUDED.last_sequence,
  last_event_id = EXCLUDED.last_event_id,
  last_source_digest = EXCLUDED.last_source_digest,
  last_event_payload_digest = EXCLUDED.last_event_payload_digest,
  gap_state = EXCLUDED.gap_state,
  updated_at = now();

UPDATE public.observation_events_raw
SET projection_status = 'COMMITTED'
WHERE EXISTS (
  SELECT 1
  FROM public.projection_events p
  WHERE p.raw_event_id = observation_events_raw.id
);

ALTER TABLE public.observation_source_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observation_machine_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observation_events_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observation_ingest_cursors ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.observation_source_bindings FROM anon, authenticated;
REVOKE ALL ON public.observation_machine_keys FROM anon, authenticated;
REVOKE ALL ON public.observation_events_raw FROM anon, authenticated;
REVOKE ALL ON public.observation_ingest_cursors FROM anon, authenticated;

GRANT SELECT ON public.observation_source_bindings TO service_role;
GRANT SELECT ON public.observation_machine_keys TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.observation_events_raw TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.observation_ingest_cursors TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.runs TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.run_gates TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.run_nodes TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.projection_events TO service_role;

DO $$
DECLARE
  seq_name text;
BEGIN
  seq_name := pg_get_serial_sequence('public.observation_events_raw','id');
  IF seq_name IS NOT NULL THEN
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', seq_name);
  END IF;
  seq_name := pg_get_serial_sequence('public.projection_events','id');
  IF seq_name IS NOT NULL THEN
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', seq_name);
  END IF;
END
$$;

REVOKE ALL ON FUNCTION public.notify_projection_event()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.notify_projection_event()
  TO service_role;

DO $$
DECLARE
  v_missing int;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='observation_source_bindings'
      AND column_name='sha_policy'
  ) THEN
    RAISE EXCEPTION 'VERIFY_SHA_POLICY_MISSING';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public'
      AND p.proname='ingest_observation_event_v2'
      AND pg_get_function_identity_arguments(p.oid)
          = 'p_source_id text, p_event jsonb, p_event_payload_digest text'
  ) THEN
    RAISE EXCEPTION 'VERIFY_SOURCE_BOUND_RPC_MISSING';
  END IF;

  SELECT count(*) INTO v_missing
  FROM public.observation_events_raw r
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.projection_events p
    WHERE p.raw_event_id = r.id
  );
  IF v_missing <> 0 THEN
    RAISE EXCEPTION 'VERIFY_RAW_PROJECTION_GAP:%', v_missing;
  END IF;

  SELECT count(*) INTO v_missing
  FROM public.observation_events_raw r
  WHERE r.gate IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM public.run_gates g
      WHERE g.gate_id = r.run_id || '::' || r.gate
        AND g.run_id = r.run_id
    );
  IF v_missing <> 0 THEN
    RAISE EXCEPTION 'VERIFY_GATE_MATERIALIZATION_GAP:%', v_missing;
  END IF;

  SELECT count(*) INTO v_missing
  FROM public.observation_events_raw r
  WHERE r.node_id IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM public.run_nodes n
      WHERE n.node_id = r.run_id || '::node::' || r.node_id
        AND n.run_id = r.run_id
    );
  IF v_missing <> 0 THEN
    RAISE EXCEPTION 'VERIFY_NODE_MATERIALIZATION_GAP:%', v_missing;
  END IF;
END
$$;
