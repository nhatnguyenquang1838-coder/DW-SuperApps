-- DW-OBS-HIST-BACKFILL-R1 · DDL (8 tables)
-- Applied ONLY after exact G6 approval via `supabase db push --linked --include-all`.
-- Idempotent: IF NOT EXISTS. GWC repo is empty; this CREATES the schema.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- runs ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
  run_id               TEXT        PRIMARY KEY,
  run_kind             TEXT        NOT NULL CHECK (run_kind IN ('observed_real','simulated_fixture','golden_fixture','reconstructed_history')),
  source_system        TEXT        NOT NULL CHECK (source_system IN ('taskcontroller','gwc','mixed')),
  epic_id              TEXT,
  jira_key             TEXT,
  parent_issue         TEXT,
  authority_ref        TEXT,
  scope_hash           TEXT,
  base_sha             TEXT,
  head_sha             TEXT,
  merge_sha            TEXT,
  base_branch          TEXT,
  branch               TEXT,
  pr_number            INTEGER,
  ci_run_id            TEXT,
  ci_status            TEXT,
  started_at           TIMESTAMPTZ,
  completed_at         TIMESTAMPTZ,
  reconstruction_basis TEXT,
  source_refs          TEXT[]      NOT NULL DEFAULT '{}',
  confidence           TEXT        CHECK (confidence IN (NULL,'HIGH','PARTIAL','UNKNOWN')),
  evidence_quality     TEXT        CHECK (evidence_quality IN (NULL,'STRONG','PARTIAL','WEAK','NONE')),
  reconstructed_by     TEXT,
  reconstructed_at     TIMESTAMPTZ,
  payload              JSONB       NOT NULL DEFAULT '{}'::jsonb
);

-- run_events ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_events (
  run_id          TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source_system   TEXT        NOT NULL,
  source_event_id TEXT        NOT NULL,
  sequence        INTEGER,
  event_type      TEXT,
  decision_kind   TEXT,
  occurred_at     TIMESTAMPTZ NOT NULL,
  gate            TEXT,
  node_id         TEXT,
  actor           JSONB,
  authority_ref   TEXT,
  payload_summary TEXT,
  evidence_refs   TEXT[]      NOT NULL DEFAULT '{}',
  version         INTEGER,
  payload         JSONB       NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (run_id, source_system, source_event_id)
);

-- run_gates -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_gates (
  gate_id        TEXT        PRIMARY KEY,
  run_id         TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  gate_label     TEXT,
  boundary       TEXT,
  authority_ref  TEXT,
  state          TEXT,
  summary        TEXT,
  node_count     INTEGER,
  artifact_count INTEGER,
  source_refs    TEXT[]      NOT NULL DEFAULT '{}'
);

-- run_nodes -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_nodes (
  node_id       TEXT        PRIMARY KEY,
  run_id        TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  gate_id       TEXT        REFERENCES run_gates(gate_id) ON DELETE SET NULL,
  family        TEXT,
  boundary      TEXT,
  state         TEXT,
  label         TEXT,
  source_refs   TEXT[]      NOT NULL DEFAULT '{}'
);

-- run_artifacts -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_artifacts (
  artifact_id              TEXT        PRIMARY KEY,
  run_id                   TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id                  TEXT,
  gate_id                  TEXT,
  artifact_type            TEXT        NOT NULL,
  artifact_status          TEXT        NOT NULL CHECK (artifact_status IN ('original','reconstructed','missing_unreconstructable')),
  original_artifact_present BOOLEAN    NOT NULL DEFAULT FALSE,
  source_occurred_at       TIMESTAMPTZ,
  effective_at             TIMESTAMPTZ,
  reconstructed_at         TIMESTAMPTZ,
  reconstruction_basis     TEXT,
  source_refs              TEXT[]      NOT NULL DEFAULT '{}',
  confidence               TEXT        CHECK (confidence IN (NULL,'HIGH','PARTIAL','UNKNOWN')),
  evidence_quality         TEXT        CHECK (evidence_quality IN (NULL,'STRONG','PARTIAL','WEAK','NONE')),
  reconstructed_by         TEXT,
  payload                  JSONB       NOT NULL DEFAULT '{}'::jsonb
);

-- run_checkpoints -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_checkpoints (
  checkpoint_id   TEXT        PRIMARY KEY,
  run_id          TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  gate_id         TEXT,
  node_id         TEXT,
  cursor          INTEGER,
  state_digest    TEXT,
  replay_digest   TEXT,
  captured_at     TIMESTAMPTZ,
  source_refs     TEXT[]      NOT NULL DEFAULT '{}'
);

-- run_edges -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_edges (
  edge_id         TEXT        PRIMARY KEY,
  run_id          TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  from_node_id    TEXT,
  to_node_id      TEXT,
  edge_kind       TEXT,
  label           TEXT,
  source_refs     TEXT[]      NOT NULL DEFAULT '{}'
);

-- run_sources ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_sources (
  source_id          TEXT        NOT NULL,
  run_id             TEXT        NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  source_system      TEXT        NOT NULL CHECK (source_system IN ('taskcontroller','gwc','github','repo_governance')),
  source_event_id    TEXT,
  source_kind        TEXT        NOT NULL CHECK (source_kind IN ('live_capture','golden_fixture','github_pr','github_issue','ci_run','gwc_artifact','reconstruction','repo_governance','controller_mailbox')),
  capture_provenance_verified BOOLEAN NOT NULL DEFAULT FALSE,
  source_ref         TEXT,
  source_digest      TEXT,
  occurred_at        TIMESTAMPTZ,
  authority_ref      TEXT,
  evidence_refs      TEXT[]      NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_run ON run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_sources_run ON run_sources(run_id);
