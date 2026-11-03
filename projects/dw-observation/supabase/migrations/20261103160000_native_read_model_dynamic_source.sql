-- Final native GWC v2 ingest/read-model contract.
-- 1) machine source_id is cryptographically authenticated by Edge and re-bound in SQL;
-- 2) exact SHA remains immutable event provenance, while trusted sources may use ANY_SIGNED;
-- 3) accepted events atomically materialize runs + gates + nodes + projection history.

ALTER TABLE observation_source_bindings
  ADD COLUMN IF NOT EXISTS sha_policy TEXT NOT NULL DEFAULT 'EXACT';

ALTER TABLE observation_source_bindings
  ALTER COLUMN source_sha DROP NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'observation_source_bindings_sha_policy_check'
      AND conrelid = 'observation_source_bindings'::regclass
  ) THEN
    ALTER TABLE observation_source_bindings
      ADD CONSTRAINT observation_source_bindings_sha_policy_check
      CHECK (
        (sha_policy = 'EXACT' AND source_sha IS NOT NULL)
        OR (sha_policy = 'ANY_SIGNED')
      );
  END IF;
END
$$;

-- Logical release source: machine identity + repository + schema authenticate the
-- publisher; every accepted event still stores and exposes its exact source_sha.
UPDATE observation_source_bindings
SET sha_policy = 'ANY_SIGNED', source_sha = NULL, updated_at = now()
WHERE source_id = 'gwc-main';

-- Fail closed: retire the old RPC shape that could not bind the authenticated source_id.
REVOKE ALL ON FUNCTION public.ingest_observation_event_v2(JSONB, TEXT)
  FROM PUBLIC, anon, authenticated, service_role;
DROP FUNCTION IF EXISTS public.ingest_observation_event_v2(JSONB, TEXT);

-- Native Universal v2 RunStateRecord starts at sequence 1 in current boot.
-- The first observed event establishes a source cursor baseline; every later
-- event must be exactly previous + 1. No missing event is fabricated.
CREATE OR REPLACE FUNCTION public.ingest_observation_event_v2(
  p_source_id TEXT,
  p_event JSONB,
  p_event_payload_digest TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_source_system TEXT;
  v_source_event_id TEXT;
  v_run_id TEXT;
  v_sequence BIGINT;
  v_existing observation_events_raw%ROWTYPE;
  v_cursor observation_ingest_cursors%ROWTYPE;
  v_raw_id BIGINT;
  v_projection_ordinal BIGINT;
  v_source_sha TEXT;
  v_source_repository TEXT;
  v_source_schema TEXT;
  v_occurred_at TIMESTAMPTZ;
  v_gate TEXT;
  v_gate_id TEXT;
  v_from_gate TEXT;
  v_runtime_state TEXT;
  v_node_source TEXT;
  v_node_id TEXT;
  v_source_refs TEXT[];
BEGIN
  IF p_event IS NULL
     OR p_event->>'schema_id' <> 'gwc.observation-event/v2'
     OR COALESCE((p_event->>'schema_version')::INT, 0) <> 2
     OR p_event #>> '{source,system}' <> 'gwc' THEN
    RAISE EXCEPTION 'SCHEMA_UNSUPPORTED' USING ERRCODE = 'P0001';
  END IF;

  v_source_system := p_event #>> '{source,system}';
  v_source_event_id := p_event->>'event_id';
  v_run_id := p_event->>'run_id';
  v_sequence := (p_event->>'sequence')::BIGINT;
  v_source_sha := p_event #>> '{source,sha}';
  v_source_repository := p_event #>> '{source,repository}';
  v_source_schema := p_event->>'schema_id';
  v_occurred_at := (p_event->>'occurred_at')::TIMESTAMPTZ;
  v_gate := p_event #>> '{runtime,gate}';
  v_runtime_state := p_event #>> '{runtime,state}';
  v_node_source := p_event #>> '{runtime,node_id}';
  v_from_gate := p_event #>> '{payload,from_gate}';
  v_gate_id := v_run_id || '::' || COALESCE(v_gate, 'UNKNOWN');
  v_node_id := CASE
    WHEN v_node_source IS NULL OR btrim(v_node_source) = '' THEN NULL
    ELSE v_run_id || '::node::' || v_node_source
  END;
  v_source_refs := ARRAY[v_source_event_id] || ARRAY(
    SELECT jsonb_array_elements_text(COALESCE(p_event->'evidence_refs','[]'::jsonb))
  );

  IF p_source_id IS NULL OR btrim(p_source_id) = ''
     OR v_source_event_id IS NULL OR v_run_id IS NULL OR v_sequence < 0
     OR v_source_sha !~ '^[0-9a-f]{40}$'
     OR p_event->>'source_digest' !~ '^sha256:[0-9a-f]{64}$'
     OR p_event_payload_digest !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'OBSERVATION_EVENT_INVALID' USING ERRCODE = 'P0001';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM observation_source_bindings b
    WHERE b.enabled
      AND b.source_id = p_source_id
      AND b.source_system = v_source_system
      AND b.source_repository = v_source_repository
      AND b.source_schema = v_source_schema
      AND (
        (COALESCE(b.sha_policy, 'EXACT') = 'EXACT' AND b.source_sha = v_source_sha)
        OR COALESCE(b.sha_policy, 'EXACT') = 'ANY_SIGNED'
      )
  ) THEN
    RAISE EXCEPTION 'SOURCE_BINDING_MISMATCH' USING ERRCODE = 'P0001';
  END IF;

  SELECT * INTO v_existing
  FROM observation_events_raw
  WHERE source_system = v_source_system
    AND source_event_id = v_source_event_id;

  IF FOUND THEN
    IF v_existing.event_payload_digest <> p_event_payload_digest THEN
      RAISE EXCEPTION 'EVENT_ID_DIGEST_CONFLICT' USING ERRCODE = 'P0001';
    END IF;
    SELECT projection_ordinal INTO v_projection_ordinal
    FROM projection_events
    WHERE raw_event_id = v_existing.id
    ORDER BY projection_ordinal DESC
    LIMIT 1;
    RETURN jsonb_build_object(
      'status','COMMITTED',
      'raw_event_id',v_existing.id,
      'projection_ordinal',v_projection_ordinal,
      'event_id',v_source_event_id,
      'payload_digest',p_event_payload_digest,
      'idempotent_replay',true
    );
  END IF;

  SELECT * INTO v_cursor
  FROM observation_ingest_cursors
  WHERE source_system = v_source_system AND run_id = v_run_id
  FOR UPDATE;

  IF FOUND THEN
    IF v_sequence <> v_cursor.last_sequence + 1 THEN
      RAISE EXCEPTION 'SOURCE_SEQUENCE_GAP' USING ERRCODE = 'P0001';
    END IF;
  END IF;

  INSERT INTO runs (
    run_id, run_kind, source_system, head_sha, started_at, source_refs, payload
  ) VALUES (
    v_run_id, 'observed_real', 'gwc', v_source_sha, v_occurred_at,
    ARRAY[v_source_event_id],
    jsonb_build_object(
      'runtime_epoch', p_event #>> '{runtime,epoch}',
      'lifecycle_profile', p_event #> '{runtime,profile}',
      'observation_contract', v_source_schema
    )
  )
  ON CONFLICT (run_id) DO UPDATE SET
    head_sha = EXCLUDED.head_sha,
    started_at = LEAST(COALESCE(runs.started_at, EXCLUDED.started_at), EXCLUDED.started_at),
    source_refs = CASE
      WHEN v_source_event_id = ANY(runs.source_refs) THEN runs.source_refs
      ELSE array_append(runs.source_refs, v_source_event_id)
    END,
    payload = runs.payload || EXCLUDED.payload;

  INSERT INTO observation_events_raw (
    source_system, source_schema, source_event_id, run_id, source_sequence,
    event_type, occurred_at, source_repository, source_sha, runtime_epoch,
    lifecycle_profile, gate, runtime_state, node_id, typed_next, outcome, actor,
    authority_ref, evidence_refs, source_digest, event_payload_digest, envelope
  ) VALUES (
    v_source_system, v_source_schema, v_source_event_id, v_run_id, v_sequence,
    p_event->>'event_type', v_occurred_at, v_source_repository, v_source_sha,
    p_event #>> '{runtime,epoch}', p_event #> '{runtime,profile}',
    p_event #>> '{runtime,gate}', p_event #>> '{runtime,state}',
    p_event #>> '{runtime,node_id}', p_event #>> '{runtime,typed_next}',
    p_event->>'outcome', p_event->'actor', p_event->>'authority_ref',
    COALESCE(p_event->'evidence_refs','[]'::jsonb),
    p_event->>'source_digest', p_event_payload_digest, p_event
  ) RETURNING id INTO v_raw_id;

  -- Materialize the functional DWO read model from the same accepted event.
  -- Gate/node IDs are run-scoped because GWC node labels can repeat across runs.
  IF v_gate IS NOT NULL AND btrim(v_gate) <> '' THEN
    IF v_from_gate IS NOT NULL AND btrim(v_from_gate) <> '' AND v_from_gate <> v_gate THEN
      UPDATE run_gates
      SET state = 'PASSED',
          summary = 'Transitioned to ' || v_gate
      WHERE gate_id = v_run_id || '::' || v_from_gate
        AND run_id = v_run_id;

      UPDATE run_nodes
      SET state = 'PASSED'
      WHERE gate_id = v_run_id || '::' || v_from_gate
        AND run_id = v_run_id;
    END IF;

    INSERT INTO run_gates (
      gate_id, run_id, gate_label, boundary, authority_ref, state, summary,
      node_count, artifact_count, source_refs
    ) VALUES (
      v_gate_id, v_run_id, v_gate, 'GWC_UNIVERSAL_V2',
      p_event->>'authority_ref', COALESCE(v_runtime_state, 'ACTIVE'),
      COALESCE(p_event->>'event_type','RUN_STATE_CHANGED') || ' / ' || COALESCE(p_event->>'outcome','UNKNOWN'),
      0, jsonb_array_length(COALESCE(p_event->'evidence_refs','[]'::jsonb)), v_source_refs
    )
    ON CONFLICT (gate_id) DO UPDATE SET
      state = EXCLUDED.state,
      authority_ref = COALESCE(EXCLUDED.authority_ref, run_gates.authority_ref),
      summary = EXCLUDED.summary,
      artifact_count = GREATEST(COALESCE(run_gates.artifact_count,0), COALESCE(EXCLUDED.artifact_count,0)),
      source_refs = run_gates.source_refs || EXCLUDED.source_refs;

    IF v_node_id IS NOT NULL THEN
      INSERT INTO run_nodes (
        node_id, run_id, gate_id, family, boundary, state, label, source_refs
      ) VALUES (
        v_node_id, v_run_id, v_gate_id, 'GWC_UNIVERSAL_V2', 'OBSERVED_RUNTIME',
        COALESCE(v_runtime_state, 'ACTIVE'), v_node_source, v_source_refs
      )
      ON CONFLICT (node_id) DO UPDATE SET
        gate_id = EXCLUDED.gate_id,
        state = EXCLUDED.state,
        label = EXCLUDED.label,
        source_refs = run_nodes.source_refs || EXCLUDED.source_refs;
    END IF;

    UPDATE run_gates g
    SET node_count = (
      SELECT count(*)::int FROM run_nodes n
      WHERE n.run_id = v_run_id AND n.gate_id = v_gate_id
    )
    WHERE g.gate_id = v_gate_id;
  END IF;

  INSERT INTO projection_events (
    run_id, source_system, source_event_id, sequence, event_type, occurred_at,
    gate, node_id, actor, outcome, before, after, evidence_refs, authority_ref,
    source_digest, read_only_projection, raw_event_id, runtime_epoch,
    lifecycle_profile, runtime_state, typed_next, source_sha
  ) VALUES (
    v_run_id, v_source_system, v_source_event_id, v_sequence, p_event->>'event_type',
    v_occurred_at, p_event #>> '{runtime,gate}', p_event #>> '{runtime,node_id}',
    p_event->'actor', p_event->>'outcome', NULL, NULL,
    COALESCE(p_event->'evidence_refs','[]'::jsonb), p_event->>'authority_ref',
    p_event->>'source_digest', TRUE, v_raw_id, p_event #>> '{runtime,epoch}',
    p_event #> '{runtime,profile}', p_event #>> '{runtime,state}',
    p_event #>> '{runtime,typed_next}', v_source_sha
  ) RETURNING projection_ordinal INTO v_projection_ordinal;

  INSERT INTO observation_ingest_cursors (
    source_system, run_id, last_sequence, last_event_id, last_source_digest,
    last_event_payload_digest, gap_state
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

  UPDATE observation_events_raw
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

REVOKE ALL ON FUNCTION public.ingest_observation_event_v2(TEXT, JSONB, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_observation_event_v2(TEXT, JSONB, TEXT)
  TO service_role;
