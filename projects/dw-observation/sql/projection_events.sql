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
-- Repository SQL producer contract (seq=16 correction): how a producer inserts
-- a projection event and how it publishes it over Broadcast. This is contract
-- SQL (read-only, no remote apply). The observer's live transport MUST agree
-- with the Broadcast shape defined here.
-- ===========================================================================
--
-- Historical insertion (producer, repository side). The producer supplies the
-- canonical envelope columns; projection_ordinal + id are assigned by Postgres,
-- so the global cross-source order is durable and authoritative.
--   INSERT INTO projection_events
--     (run_id, source_system, source_event_id, sequence, event_type,
--      occurred_at, gate, node_id, actor, outcome, before, after,
--      evidence_refs, authority_ref, source_digest)
--   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15);
--
-- Broadcast publish contract (live transport). The producer publishes on:
--   topic  = 'observatory:' || <run_id>     -- NOT the event name
--   event  = 'projection_event'             -- FIXED event name, distinct from topic
--   type   = 'broadcast'
--   payload = <ProjectionEvent>             -- the canonical envelope object
-- The subscriber (lib/supabaseRealtime.ts + LiveProjectionClient.receiveLive)
-- binds channel.on('broadcast', { event: 'projection_event' }, ...) on the
-- 'observatory:<run_id>' topic and reads payload as the ProjectionEvent.

-- Durable read contract (used by PostgresEventStore.loadAll in
-- lib/postgresEventStore.ts). Historical source of truth only — read, never
-- insert/update/delete from the observer. Ordered by the durable global
-- ordinal so mixed TC/GWC interleaving is preserved exactly.
--   SELECT run_id, source_system, source_event_id, sequence, event_type,
--          occurred_at, gate, node_id, actor, outcome, before, after,
--          evidence_refs, authority_ref, source_digest, read_only_projection
--   FROM projection_events
--   WHERE run_id = $1
--   ORDER BY projection_ordinal;
