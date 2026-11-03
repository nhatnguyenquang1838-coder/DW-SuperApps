-- DWO v2 native GWC observation feed.
-- Durable-first: immutable raw ledger -> deterministic projection -> Realtime.
-- Non-production rollout is governed separately from production effects.

CREATE TABLE IF NOT EXISTS observation_source_bindings (
  source_id         TEXT PRIMARY KEY,
  source_system     TEXT NOT NULL,
  source_repository TEXT NOT NULL,
  source_sha        TEXT NOT NULL CHECK (source_sha ~ '^[0-9a-f]{40}$'),
  source_schema     TEXT NOT NULL,
  enabled           BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observation_machine_keys (
  key_id       TEXT PRIMARY KEY,
  source_id    TEXT NOT NULL REFERENCES observation_source_bindings(source_id) ON DELETE CASCADE,
  secret_hash  TEXT NOT NULL CHECK (secret_hash ~ '^sha256:[0-9a-f]{64}$'),
  enabled      BOOLEAN NOT NULL DEFAULT TRUE,
  expires_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observation_events_raw (
  id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_system        TEXT NOT NULL,
  source_schema        TEXT NOT NULL,
  source_event_id      TEXT NOT NULL,
  run_id               TEXT NOT NULL,
  source_sequence      BIGINT NOT NULL CHECK (source_sequence >= 0),
  event_type           TEXT NOT NULL,
  occurred_at          TIMESTAMPTZ NOT NULL,
  received_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_repository    TEXT NOT NULL,
  source_sha           TEXT NOT NULL CHECK (source_sha ~ '^[0-9a-f]{40}$'),
  runtime_epoch        TEXT,
  lifecycle_profile    JSONB,
  gate                 TEXT,
  runtime_state        TEXT,
  node_id              TEXT,
  typed_next           TEXT,
  outcome              TEXT,
  actor                JSONB,
  authority_ref        TEXT,
  evidence_refs        JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_digest        TEXT NOT NULL CHECK (source_digest ~ '^sha256:[0-9a-f]{64}$'),
  event_payload_digest TEXT NOT NULL CHECK (event_payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  envelope             JSONB NOT NULL,
  projection_status    TEXT NOT NULL DEFAULT 'PENDING'
                         CHECK (projection_status IN ('PENDING','COMMITTED','FAILED')),
  UNIQUE (source_system, source_event_id),
  UNIQUE (source_system, run_id, source_sequence)
);

CREATE TABLE IF NOT EXISTS observation_ingest_cursors (
  source_system             TEXT NOT NULL,
  run_id                    TEXT NOT NULL,
  last_sequence             BIGINT NOT NULL,
  last_event_id             TEXT NOT NULL,
  last_source_digest        TEXT NOT NULL,
  last_event_payload_digest TEXT NOT NULL,
  gap_state                 TEXT NOT NULL DEFAULT 'NONE',
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (source_system, run_id)
);

CREATE INDEX IF NOT EXISTS idx_observation_raw_run_seq
  ON observation_events_raw (source_system, run_id, source_sequence);
CREATE INDEX IF NOT EXISTS idx_observation_raw_received
  ON observation_events_raw (received_at);

ALTER TABLE projection_events
  ADD COLUMN IF NOT EXISTS raw_event_id BIGINT,
  ADD COLUMN IF NOT EXISTS runtime_epoch TEXT,
  ADD COLUMN IF NOT EXISTS lifecycle_profile JSONB,
  ADD COLUMN IF NOT EXISTS runtime_state TEXT,
  ADD COLUMN IF NOT EXISTS typed_next TEXT,
  ADD COLUMN IF NOT EXISTS source_sha TEXT;

CREATE INDEX IF NOT EXISTS idx_projection_events_raw_event_id
  ON projection_events (raw_event_id);

ALTER TABLE observation_source_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation_machine_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation_events_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE observation_ingest_cursors ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON observation_source_bindings FROM anon, authenticated;
REVOKE ALL ON observation_machine_keys FROM anon, authenticated;
REVOKE ALL ON observation_events_raw FROM anon, authenticated;
REVOKE ALL ON observation_ingest_cursors FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.ingest_observation_event_v2(
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

  IF v_source_event_id IS NULL OR v_run_id IS NULL OR v_sequence < 0
     OR v_source_sha !~ '^[0-9a-f]{40}$'
     OR p_event->>'source_digest' !~ '^sha256:[0-9a-f]{64}$'
     OR p_event_payload_digest !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'OBSERVATION_EVENT_INVALID' USING ERRCODE = 'P0001';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM observation_source_bindings b
    WHERE b.enabled
      AND b.source_system = v_source_system
      AND b.source_repository = v_source_repository
      AND b.source_sha = v_source_sha
      AND b.source_schema = v_source_schema
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
  ELSE
    IF v_sequence <> 0 THEN
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

REVOKE ALL ON FUNCTION public.ingest_observation_event_v2(JSONB, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_observation_event_v2(JSONB, TEXT)
  TO service_role;

CREATE OR REPLACE FUNCTION public.notify_projection_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, realtime
AS $
BEGIN
  PERFORM realtime.send(
    jsonb_build_object(
      'run_id', NEW.run_id,
      'source_system', NEW.source_system,
      'source_event_id', NEW.source_event_id,
      'sequence', NEW.sequence,
      'projection_ordinal', NEW.projection_ordinal,
      'event_type', NEW.event_type,
      'occurred_at', NEW.occurred_at,
      'gate', NEW.gate,
      'node_id', NEW.node_id,
      'actor', NEW.actor,
      'outcome', NEW.outcome,
      'before', NEW.before,
      'after', NEW.after,
      'evidence_refs', NEW.evidence_refs,
      'authority_ref', NEW.authority_ref,
      'source_digest', NEW.source_digest,
      'read_only_projection', NEW.read_only_projection,
      'raw_event_id', NEW.raw_event_id,
      'runtime_epoch', NEW.runtime_epoch,
      'lifecycle_profile', NEW.lifecycle_profile,
      'runtime_state', NEW.runtime_state,
      'typed_next', NEW.typed_next,
      'source_sha', NEW.source_sha
    ),
    'projection_event',
    'observatory:' || NEW.run_id,
    false
  );
  RETURN NEW;
END;
$$;

ALTER FUNCTION public.notify_projection_event() SET search_path = pg_catalog, public;
