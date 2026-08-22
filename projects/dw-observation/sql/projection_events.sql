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
--     NOT invented by the observer.
--
-- Historical replay reads projection_events ordered by (run_id, source_system,
-- sequence) — never by arrival time. Live delivery is a separate transport.

CREATE TABLE IF NOT EXISTS projection_events (
  id              BIGGENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id          TEXT        NOT NULL,
  source_system   TEXT        NOT NULL
                    CHECK (source_system IN ('taskcontroller', 'gwc')),
  source_event_id TEXT        NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_projection_events_run_seq
  ON projection_events (run_id, source_system, sequence);

-- Durable read contract (used by PostgresEventStore.loadAll in
-- lib/postgresEventStore.ts). Historical source of truth only — read, never
-- insert/update/delete from the observer.
--   SELECT run_id, source_system, source_event_id, sequence, event_type,
--          occurred_at, gate, node_id, actor, outcome, before, after,
--          evidence_refs, authority_ref, source_digest, read_only_projection
--   FROM projection_events
--   WHERE run_id = $1
--   ORDER BY source_system, sequence;
