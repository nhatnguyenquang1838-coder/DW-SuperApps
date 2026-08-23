# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · G6 APPROVAL PACKET

**STOP — human authority required before any remote apply.**

## Target
- Supabase project: `auswvdxoetufwiaxutib`
- Schema: `public`
- Current state (verified by Controller): `public` tables = `[]`, migrations = `[]`
- No target schema exists yet → this migration CREATES it.

## Migration
- File: `projects/dw-observation/supabase/migrations/20260823T080000Z_observatory_history.sql`
- SHA-256: `ba0b7b2eeb59be905739562e9ee287f982b46a3bbee2a70e5f759a4526613e22`
- Tables (8): `runs`, `run_gates`, `run_nodes`, `run_events`, `run_artifacts`,
  `run_checkpoints`, `run_edges`, `run_sources`
- `run_kind` enum: `observed_real | simulated_fixture | golden_fixture | reconstructed_history`
- `run_sources.source_kind` enum: `live_capture | golden_fixture | github_pr |
  github_issue | ci_run | gwc_artifact | reconstruction` (+ `capture_provenance_verified`,
  `source_ref`, `source_digest`)
- Idempotent: `CREATE TABLE IF NOT EXISTS`, event upsert key
  `UNIQUE(run_id, source_system, source_event_id)`, FK cascade, `IF NOT EXISTS` indexes.
- No `created_at` falsification; ingestion defaults `now()`.

## Dry-run row counts (deterministic, corrected classification)
| Table | Rows |
|-------|------|
| runs | 8 |
| run_events | 12 |
| run_gates | 1 |
| run_nodes | 2 |
| run_artifacts | 0 |
| run_checkpoints | 0 |
| run_edges | 0 |
| run_sources | 2 |

By `run_kind`: **`golden_fixture` = 2, `reconstructed_history` = 6, `observed_real` = 0**.

## Validation results (offline, no remote)
- Referential integrity: PASS (0 violations)
- Idempotency / upsert keys: PASS (0 conflicts)
- No duplicate run rows: PASS (0)
- Real-vs-simulated separation: PASS (`observed_real = 0`; fixtures are `golden_fixture`, not masquerading as live capture)
- Reconstruction provenance: PASS (all reconstructed rows carry basis/source_refs/confidence; golden rows carry `source_kind` + `capture_provenance_verified=false`)
- Deterministic row counts: PASS (reproducible via `scripts/backfillHistoricalRuns.ts`)
- Rollback plan: PASS (`DROP TABLE ... CASCADE` provided)

## Reconstructed / missing (corrected)
- `observed_real` (live): **0**
- `golden_fixture`: 2
- `reconstructed_history`: 6
- Missing / unreconstructable: 0

## Exact approval command (binding G6)
```
supabase db push --project-ref auswvdxoetufwiaxutib \
  --include-all \
  --file projects/dw-observation/supabase/migrations/20260823T080000Z_observatory_history.sql
# then run backfill (dry-run already validated):
#   DW_OBS_PROJECT_ROOT=. node scripts/backfillHistoricalRuns.ts   # (--apply with G6 token)
```
DO NOT execute until exact G6 approval is bound. This packet is the boundary artifact only.

## Exclusions honored
- No remote Supabase apply (G6 boundary) — STOP here.
- PR #81 untouched / unmerged (separate DRAFT UI run at `76670a5`).
- No `pre-prod -> main`, no deploy, no GWC mutation, no force-push/rewrite.
- Branch: `auto/SCRUM-555-observatory-history-backfill` (from `pre-prod@a992fa48`).
