# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · G6 APPROVAL PACKET

**STOP — human authority required before any remote apply.**

## Target
- Supabase project: `auswvdxoetufwiaxutib`
- Schema: `public`
- Current state (verified by Controller): `public` tables = `[]`, migrations = `[]`
- No target schema exists yet → DDL migration CREATES it.

## Migrations (both DRAFT, G6-gated)
- DDL: `projects/dw-observation/supabase/migrations/20260823T080000Z_observatory_history.sql`
  - SHA-256: `f71bdfd86013346bc77e6ea1bc65ef4d593df6a386e972b2009694ac278663a7`
- DML (deterministic backfill, idempotent ON CONFLICT): `supabase/migrations/20260823T090000Z_observatory_backfill_dml.sql`
  - SHA-256: `e4dac6fba752f98b2967e2bacf146d79742bd25872b288fe329e567cbdcf7857`
- Tables (8): `runs` (8), `run_events` (12), `run_gates` (1), `run_nodes` (2),
  `run_artifacts` (25), `run_checkpoints` (0), `run_edges` (0), `run_sources` (21).
- `run_kind` enum: `observed_real | simulated_fixture | golden_fixture | reconstructed_history`
- `run_sources.source_kind`: `live_capture | golden_fixture | github_pr | github_issue | ci_run | gwc_artifact | reconstruction`.
- `run_artifacts.artifact_status`: `original | reconstructed | missing_unreconstructable`.
- `evidence_quality` now includes `PARTIAL` (CI inferred from PR where no run captured).
- Idempotent: `IF NOT EXISTS` DDL, event upsert key `UNIQUE(run_id, source_system, source_event_id)`,
  DML `ON CONFLICT DO NOTHING`. No `created_at` falsification (ingestion defaults `now()`).

## Offline dry-run (deterministic)
- Digest (normalized rows): `babe50de9e62468d2f51aff6b656738df92668c003a732ec882726811e27a4db`
  (identical across two runs with `DW_OBS_RECONSTRUCTED_AT=2026-08-23T08:30:00.000Z`).
- Real TypeScript type-check (node compiler API, strict): PASS.
- RI: PASS (0 violations). Idempotency: PASS (0 upsert conflicts).
- No duplicate run rows. Real-vs-sim separation: PASS (`observed_real=0`).
- Provenance: PASS (each reconstructed run ≥1 source; each artifact references source evidence).
- Artifact status breakdown: **reconstructed=23, original=1, missing_unreconstructable=1**.

## Exact remote-apply command (validated against installed CLI)
Installed: `supabase` CLI **2.111.0**. Correct workflow (per `supabase db push --help`):
```
# 1) link the project once (interactive or via env):
supabase link --project-ref auswvdxoetufwiaxutib
# 2) dry-run to preview:
supabase db push --linked --dry-run
# 3) apply DDL + DML only after exact G6 approval:
supabase db push --linked --include-all
#   then run the deterministic DML migration against the linked DB:
#   psql "$DB_URL" -f supabase/migrations/20260823T090000Z_observatory_backfill_dml.sql
```
NOTE: earlier packet's `supabase db push --project-ref ... --file ...` was WRONG
(the CLI has no `--project-ref`/`--file` on `db push`). Corrected above.

## Reconstructed / missing (artifact status, not run_kind)
- `original`: 1 (`M3-M4-EVIDENCE.md` as `historical_evidence_file`)
- `reconstructed`: 23 (context/delivery/ci/alignment per run)
- `missing_unreconstructable`: 1 (M4 `gate_canonical_artifact` — no evidence; recorded, not invented)
- `observed_real` (live): 0

## Lifecycle status (per seq=9 correction A)
- G2 package: COMPLETE (this branch).
- G3 Draft PR: to be opened (this run) → `auto/SCRUM-555-observatory-history-backfill` → `pre-prod`.
- G4 exact-head merge authority: NOT done.
- G5 read-only merged-head status: NOT done.
- G6 remote DDL/DML: **STOP — blocked until exact G6 approval bound.**
- PR #81: untouched / unmerged (separate DRAFT UI run at `76670a5`).

## Exclusions honored
- No remote Supabase apply (G6 boundary) — STOP here.
- No `pre-prod -> main`, no deploy, no GWC mutation, no force-push/rewrite.
