-- M2 — DW Run Observatory durable projection event store (Postgres).
--
-- Repository-only schema artifact. This file is the canonical DDL for the
-- durable projection event store. It is committed for review and applied by
-- the host platform / migrations tooling. The M2 executor performs NO remote
-- apply/mutation: this artifact is read-only contract code, not an applied
-- migration. (remote_db_mutation = false)
--
-- Source of truth contract:
--   * The durable store is the canonical historical source for a run's
--     projected events. The browser never treats Realtime Broadcast as history.
--   * Every row is the same normalized RunProjectionEvent v1 envelope produced
--     by dw_observation/events.py (frozen, read-only, exact-source provenance).
--   * sequence is the SOURCE ledger sequence per (run_id, source_system) and is
--     NOT invented by the observer. It is used ONLY for per-source gap/duplicate
--     detection on the live path.
--
-- CROSS-SOURCE ORDERING (seq=16 correction): historical replay is ordered by a
-- durable GLOBAL ordinal, NOT by occurred_at and NOT by per-source grouping.
-- projection_ordinal is a BIGINT GENERATED ALWAYS AS IDENTITY assigned at insert
-- time, so it is the authoritative cross-source (mixed taskcontroller/gwc)
-- insertion order that preserves the true interleaving of the run.

CREATE TABLE IF NOT EXISTS projection_events (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  -- Durable global cross-source order. Assigned at insert; the canonical
  -- historical ORDER BY key for a run (mixed TC/GWC interleaving preserved).
  projection_ordinal BIGINT GENERATED ALWAYS AS IDENTITY,
  run_id          TEXT        NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_projection_events_run_ordinal
  ON projection_events (run_id, projection_ordinal);

CREATE INDEX IF NOT EXISTS idx_projection_events_run_src_seq
  ON projection_events (run_id, source_system, sequence);

-- ===========================================================================
-- Repository SQL producer contract (seq=16 + R4_B4 correction): how a producer
-- inserts a projection event AND publishes it over Supabase Realtime Broadcast.
--
-- This is CONTRACT SQL: executable, reviewable function/trigger definitions that
-- define the canonical publish semantics. They are committed for review; the
-- executor performs NO remote apply/mutation (remote_db_mutation = false). No
-- RLS/policy/Realtime-config DDL is included — only the producer contract.
--
-- Independent semantic review required the producer to be EXECUTABLE
-- (realtime.send(...) + trigger), not comment-only.
-- ===========================================================================

-- Broadcast publish contract (live transport). The producer publishes on:
--   topic  = 'observatory:' || <run_id>     -- NOT the event name
--   event  = 'projection_event'             -- FIXED event name, distinct from topic
--   type   = 'broadcast'
--   payload = <ProjectionEvent>             -- the canonical envelope object
-- The subscriber (lib/supabaseRealtime.ts + LiveProjectionClient.receiveLive)
-- binds channel.on('broadcast', { event: 'projection_event' }, ...) on the
-- 'observatory:<run_id>' topic and reads payload as the ProjectionEvent.

-- Executable producer function: builds the canonical RAW ProjectionEvent jsonb
-- from the freshly inserted durable row and ships it as the payload of
-- realtime.send().
--
-- CRITICAL (R4.1 blocker fix): the FIRST argument to realtime.send() is the
-- RAW ProjectionEvent (the row columns as jsonb), NOT a nested Broadcast
-- envelope. Supabase Database Broadcast wraps the first argument into the
-- delivered callback frame as `payload`:
--   { type: 'broadcast', event: <event>, payload: <first_arg> }
-- so <first_arg> is exactly what the subscriber receives as `payload`. If we
-- instead passed a nested {type,event,topic,payload} envelope, the subscriber
-- would receive `payload.payload` and the live ProjectionEvent would NOT be at
-- top-level (risk of REJECTED because source_system/source_event_id would be
-- missing at the top level).
--
-- The topic is the channel ('observatory:' || run_id); the event is the fixed
-- 'projection_event' name. is_private=false keeps the broadcast readable by any
-- authenticated subscriber in the run's topic (transport-only; not canonical
-- history). This function performs NO mutation beyond the Broadcast send — the
-- row already exists (AFTER INSERT trigger).
CREATE OR REPLACE FUNCTION notify_projection_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  payload jsonb;
BEGIN
  -- RAW ProjectionEvent jsonb (row columns) — this is the object the
  -- subscriber receives as the callback `payload` (top-level source identity).
  payload := jsonb_build_object(
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
  );
  -- Supabase Database Broadcast: realtime.send(payload, event, topic, is_private)
  -- payload = RAW ProjectionEvent jsonb (row columns) — NOT a nested envelope.
  -- topic = 'observatory:' || run_id ; event = 'projection_event'.
  PERFORM realtime.send(payload, 'projection_event', 'observatory:' || NEW.run_id, false);
  RETURN NEW;
END;
$$;

-- AFTER INSERT trigger: every durable projection_events row fires the
-- Broadcast producer exactly once, so the live transport receives canonical
-- frames in durable (projection_ordinal) order.
DROP TRIGGER IF EXISTS trg_projection_event_broadcast ON projection_events;
CREATE TRIGGER trg_projection_event_broadcast
  AFTER INSERT ON projection_events
  FOR EACH ROW
  EXECUTE FUNCTION notify_projection_event();

-- Historical insertion (producer, repository side). The producer supplies the
-- canonical envelope columns; projection_ordinal + id are assigned by Postgres,
-- so the global cross-source order is durable and authoritative. Shown as
-- reference for the host migration tooling (not executed here).
--   INSERT INTO projection_events
--     (run_id, source_system, source_event_id, sequence, event_type,
--      occurred_at, gate, node_id, actor, outcome, before, after,
--      evidence_refs, authority_ref, source_digest)
--   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15);

-- Durable read contract (used by PostgresEventStore.loadAll in
-- lib/postgresEventStore.ts). Historical source of truth only — read, never
-- insert/update/delete from the observer. Ordered by the durable global
-- ordinal so mixed TC/GWC interleaving is preserved exactly.
--   SELECT run_id, source_system, source_event_id, sequence, projection_ordinal,
--          event_type, occurred_at, gate, node_id, actor, outcome, before,
--          after, evidence_refs, authority_ref, source_digest,
--          read_only_projection
--   FROM projection_events
--   WHERE run_id = $1
--   ORDER BY projection_ordinal;

