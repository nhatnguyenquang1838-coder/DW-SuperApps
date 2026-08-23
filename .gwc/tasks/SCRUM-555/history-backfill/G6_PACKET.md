# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · G6 APPROVAL PACKET

**STOP — human authority required before any remote apply.**

## Target
- Supabase project: `auswvdxoetufwiaxutib`
- Schema: `public`
- Current state (verified by Controller): `public` tables = `[]`, migrations = `[]`
- No target schema exists yet → this migration CREATES it.

## Migration
- File: `projects/dw-observation/supabase/migrations/20260823T080000Z_observatory_history.sql`
- SHA-256: `37986b9568d1535b04c8f3777d95db2f5dda5878410c3711682326fc76a4145d`
- Tables (8): `runs`, `run_gates`, `run_nodes`, `run_events`, `run_artifacts`,
  `run_checkpoints`, `run_edges`, `run_sources`
- Idempotent: all `CREATE TABLE IF NOT EXISTS`, event upsert key
  `UNIQUE(run_id, source_system, source_event_id)`, FK cascade, indexes `IF NOT EXISTS`.
- No `created_at` falsification; ingestion timestamps default `now()`.

## Dry-run row counts (deterministic, reproducible)
| Table | Rows |
|-------|------|
| runs | 8 |
| run_events | 12 |
| run_gates | 1 |
| run_nodes | 2 |
| run_artifacts | 0 |
| run_checkpoints | 0 |
| run_edges | 0 |
| run_sources | 0 |

By `run_kind`: `observed_real` = 2, `reconstructed_history` = 6, `simulated_fixture` = 0.

## Validation results (offline, no remote)
- Referential integrity: PASS (0 violations — all gates/nodes/events reference existing runs)
- Idempotency / upsert keys: PASS (0 conflicts)
- No duplicate run rows: PASS (0)
- Real-vs-simulated separation: PASS (0 simulated rows)
- Reconstruction provenance: PASS (all 6 reconstructed rows carry basis/source_refs/confidence)
- Deterministic row counts: PASS (reproducible via `scripts/backfillHistoricalRuns.ts`)
- Rollback plan: PASS (`DROP TABLE ... CASCADE` provided)

## Reconstructed / missing
- Reconstructed (run rows): 6
- Missing / unreconstructable: 0
- Original artifacts present: 4 (2 event streams + 2 projections)

## Exact approval command (binding G6)
```
# After exact G6 approval is granted and bound, apply via Supabase CLI/migrations:
supabase db push --project-ref auswvdxoetufwiaxutib \
  --include-all \
  --file projects/dw-observation/supabase/migrations/20260823T080000Z_observatory_history.sql
# then run the backfill (dry-run already validated):
#   DW_OBS_PROJECT_ROOT=. node scripts/backfillHistoricalRuns.ts   # (--apply with G6 token)
```
DO NOT execute the above until exact G6 approval is bound. This packet is the
boundary artifact only.

## Exclusions honored
- No remote Supabase apply (G6 boundary) — STOP here.
- PR #81 untouched / unmerged (separate DRAFT UI run at `76670a5`).
- No `pre-prod -> main`, no deploy, no GWC mutation, no force-push/rewrite.
- Branch: `auto/SCRUM-555-observatory-history-backfill` (from `pre-prod@a992fa48`).
