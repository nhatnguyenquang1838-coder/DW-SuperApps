-- DW-OBS-G6-READINESS-R1 · projection_events canonical ledger
-- Exactly ONE new migration for the approved single projection_events contract.
-- Aligned to canonical projects/dw-observation/sql/projection_events.sql
-- (RunProjectionEvent v1, DB-assigned global ordinal, full normalized envelope).
-- G6-specific Supabase deployment requirements preserved:
--   FK run_id REFERENCES runs(run_id) ON DELETE CASCADE,
--   RLS enabled, SELECT-only policy for anon, authenticated.
-- No historical backfill; no client write path.

CREATE TABLE IF NOT EXISTS projection_events (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  -- Durable global cross-source order. Assigned at insert by Postgres; the
  -- canonical historical ORDER BY key for a run (mixed TC/GWC interleaving
  -- preserved). DB-assigned so the producer never invents a non-monotonic value.
  projection_ordinal BIGINT GENERATED ALWAYS AS IDENTITY,
  run_id          TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source_system   TEXT        NOT NULL
                    CHECK (source_system IN ('taskcontroller', 'gwc')),
  source_event_id TEXT        NOT NULL,
  -- Per-source ledger sequence. Used only for per-source gap/duplicate logic
  -- on the live path; NOT the cross-source historical order.
  sequence        INTEGER     NOT NULL CHECK (sequence >= 0),
  event_type      TEXT        NOT NULL,
  occurred_at     TIMESTAMPTZ NOT NULL,
  gate            TEXT,
  node_id         TEXT,
  actor           JSONB,
  outcome         TEXT,
  before          JSONB,
  after           JSONB,
  evidence_refs   JSONB,
  authority_ref   TEXT,
  source_digest   TEXT        NOT NULL,
  read_only_projection BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (run_id, source_system, source_event_id)  -- identity; dup = DUPLICATE
);

-- Strict deterministic per-run ordering: no two events in the same run may
-- share the same projection_ordinal. UNIQUE INDEX (in addition to the global
-- IDENTITY itself which is globally unique).
CREATE UNIQUE INDEX IF NOT EXISTS idx_projection_events_run_ordinal
  ON projection_events (run_id, projection_ordinal);

-- Per-source gap/duplicate detection index.
CREATE INDEX IF NOT EXISTS idx_projection_events_run_src_seq
  ON projection_events (run_id, source_system, sequence);

-- Broadcast publish contract (live transport). The producer publishes on:
--   topic  = 'observatory:' || run_id     -- NOT the event name
--   event  = 'projection_event'           -- FIXED event name, distinct from topic
--   payload = RAW normalized ProjectionEvent (row columns as jsonb) — NOT a
--             nested envelope and NOT a ::text cast.
--
-- The FIRST argument to realtime.send() is the RAW ProjectionEvent jsonb. Supabase
-- Database Broadcast wraps it as { type: 'broadcast', event: <event>, payload: <first_arg> },
-- so the subscriber receives exactly the canonical ProjectionEvent at top level.
--
-- CRITICAL: do NOT cast the payload to ::text — that would stringify the envelope
-- and break the subscriber's top-level source identity expectations.

CREATE OR REPLACE FUNCTION notify_projection_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  -- RAW normalized ProjectionEvent jsonb (all canonical row columns) — this is
  -- the object the subscriber receives as the callback `payload` (top-level
  -- source identity). Includes sequence, projection_ordinal, gate, node_id,
  -- actor, outcome, before, after, evidence_refs, authority_ref, source_digest,
  -- read_only_projection at top level (NOT nested under a 'payload' key).
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
      'read_only_projection', NEW.read_only_projection
    ),
    'projection_event',
    'observatory:' || NEW.run_id,
    false
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_projection_events_after_insert
  AFTER INSERT ON projection_events
  FOR EACH ROW
  EXECUTE FUNCTION notify_projection_event();

ALTER TABLE projection_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY projection_events_select_publishable
  ON projection_events FOR SELECT TO anon, authenticated USING (true);
