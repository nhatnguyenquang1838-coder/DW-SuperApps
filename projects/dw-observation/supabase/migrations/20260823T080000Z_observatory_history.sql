-- DW-OBS-HIST-BACKFILL-R1 · historical Run backfill → Supabase
-- Migration: 20260823T080000Z_observatory_history.sql
--
-- Target project: auswvdxoetufwiaxutib (public schema)
-- Status: DRAFT migration artifact. NOT applied remotely (G6 boundary).
-- remote_db_mutation = false  (applied only after exact G6 approval bound)
--
-- Design basis: extends M2 durable projection event store (sql/projection_events.sql)
-- with normalized run/gate/node/event/artifact/checkpoint/edge/source tables.
-- All provenance + reconstruction fields preserved; no created_at falsification.

-- ===========================================================================
-- 1. runs  (one row per inventoried historical run)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS runs (
  run_id            TEXT        PRIMARY KEY,
  run_kind          TEXT        NOT NULL
                      CHECK (run_kind IN ('observed_real','simulated_fixture','reconstructed_history')),
  source_system     TEXT        NOT NULL
                      CHECK (source_system IN ('taskcontroller','gwc','mixed')),
  epic_id           TEXT,
  jira_key          TEXT,
  parent_issue      TEXT,
  authority_ref     TEXT,
  scope_sha         TEXT,                      -- exact execution base SHA
  base_branch       TEXT,
  branch            TEXT,
  pr_number         INTEGER,
  ci_run_id         TEXT,
  ci_status         TEXT,
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  -- reconstruction provenance (null for observed_real)
  reconstruction_basis   TEXT,
  source_refs        TEXT[]   NOT NULL DEFAULT '{}',
  confidence         TEXT      CHECK (confidence IN (NULL,'HIGH','PARTIAL','UNKNOWN')),
  evidence_quality   TEXT      CHECK (evidence_quality IN (NULL,'STRONG','WEAK','NONE')),
  reconstructed_by   TEXT,
  reconstructed_at   TIMESTAMPTZ,
  payload            JSONB     NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===========================================================================
-- 2. run_gates  (authority-boundary gates per run)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_gates (
  gate_id           TEXT        NOT NULL,
  run_id            TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  gate_label        TEXT,
  boundary          TEXT,                      -- read_only / g2_execution_boundary / ...
  authority_ref     TEXT,
  state             TEXT,
  summary           TEXT,
  node_count        INTEGER,
  artifact_count    INTEGER,
  payload           JSONB       NOT NULL DEFAULT '{}'::jsonb,
  source_refs       TEXT[]      NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, gate_id)
);

-- ===========================================================================
-- 3. run_nodes  (runtime nodes inside gates)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_nodes (
  node_id           TEXT        NOT NULL,
  run_id            TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  gate_id           TEXT        NOT NULL,
  family            TEXT,
  boundary          TEXT,
  state             TEXT,
  label             TEXT,
  payload           JSONB       NOT NULL DEFAULT '{}'::jsonb,
  source_refs       TEXT[]      NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, node_id),
  FOREIGN KEY (run_id, gate_id) REFERENCES run_gates(run_id, gate_id) ON DELETE CASCADE
);

-- ===========================================================================
-- 4. run_events  (canonical durable event stream, extends M2 envelope)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_events (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_ordinal BIGINT GENERATED ALWAYS AS IDENTITY,   -- cross-source order
  run_id            TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source_system     TEXT        NOT NULL CHECK (source_system IN ('taskcontroller','gwc')),
  source_event_id   TEXT        NOT NULL,
  sequence          INTEGER     NOT NULL CHECK (sequence >= 0),
  event_type        TEXT        NOT NULL,
  decision_kind     TEXT,
  occurred_at       TIMESTAMPTZ NOT NULL,
  gate              TEXT,
  node_id           TEXT,
  actor             JSONB,
  authority_ref     TEXT,
  payload_summary   TEXT,
  raw_payload_ref   TEXT,
  before            JSONB,
  after             JSONB,
  evidence_refs     TEXT[]      NOT NULL DEFAULT '{}',
  annotations       JSONB       NOT NULL DEFAULT '{}'::jsonb,
  version           INTEGER,
  payload           JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (run_id, source_system, source_event_id)   -- idempotent upsert key
);

-- ===========================================================================
-- 5. run_artifacts  (with reconstruction provenance — NO created_at falsification)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_artifacts (
  artifact_id           TEXT        NOT NULL,
  run_id                TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id               TEXT,
  gate_id               TEXT,
  artifact_type         TEXT,
  -- provenance / reconstruction
  artifact_status       TEXT        NOT NULL DEFAULT 'original'
                            CHECK (artifact_status IN ('original','reconstructed','missing_unreconstructable')),
  original_artifact_present BOOLEAN NOT NULL DEFAULT true,
  source_occurred_at    TIMESTAMPTZ,             -- historical event time (truthful)
  effective_at          TIMESTAMPTZ,             -- if needed
  reconstructed_at      TIMESTAMPTZ,             -- actual current time (truthful)
  reconstruction_basis  TEXT,
  source_refs           TEXT[]      NOT NULL DEFAULT '{}',
  confidence            TEXT        CHECK (confidence IN (NULL,'HIGH','PARTIAL','UNKNOWN')),
  evidence_quality      TEXT        CHECK (evidence_quality IN (NULL,'STRONG','WEAK','NONE')),
  reconstructed_by      TEXT,
  payload               JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),   -- ingestion time, NEVER backdated
  PRIMARY KEY (run_id, artifact_id)
);

-- ===========================================================================
-- 6. run_checkpoints  (runtime checkpoints)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_checkpoints (
  checkpoint_id      TEXT        NOT NULL,
  run_id             TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id            TEXT,
  gate_id            TEXT,
  state              TEXT,
  cursor             INTEGER,
  state_digest       TEXT,
  occurred_at        TIMESTAMPTZ,
  payload            JSONB       NOT NULL DEFAULT '{}'::jsonb,
  source_refs        TEXT[]      NOT NULL DEFAULT '{}',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, checkpoint_id)
);

-- ===========================================================================
-- 7. run_edges  (gate→gate / node→node dependencies)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_edges (
  edge_id            TEXT        NOT NULL,
  run_id             TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source             TEXT,
  target             TEXT,
  kind               TEXT        CHECK (kind IN ('route','fanout','dependency')),
  active             BOOLEAN,
  payload            JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, edge_id)
);

-- ===========================================================================
-- 8. run_sources  (source-system ledger provenance per run)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS run_sources (
  source_id          TEXT        NOT NULL,
  run_id             TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source_system      TEXT        NOT NULL CHECK (source_system IN ('taskcontroller','gwc')),
  source_event_id    TEXT,
  occurred_at        TIMESTAMPTZ,
  authority_ref      TEXT,
  evidence_refs      TEXT[]      NOT NULL DEFAULT '{}',
  payload            JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, source_id)
);

-- ===========================================================================
-- Indexes (deterministic, idempotent)
-- ===========================================================================
CREATE INDEX IF NOT EXISTS idx_run_events_run_ordinal ON run_events(run_id, projection_ordinal);
CREATE INDEX IF NOT EXISTS idx_run_nodes_gate ON run_nodes(run_id, gate_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_status ON run_artifacts(run_id, artifact_status);
CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(run_kind);
