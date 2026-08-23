# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · G6 APPROVAL PACKET

**STOP — human authority required before any remote apply.**

## Target
- Supabase project: `auswvdxoetufwiaxutib`
- Schema: `public`
- Current state (verified by Controller): `public` tables = `[]`, migrations = `[]`
- DDL migration CREATES the schema (no target exists yet).

## Migrations (both committed under `supabase/migrations/`, G6-gated)
- DDL: `20260823T080000Z_observatory_history.sql`
  - SHA-256: `06a31fe0217dbdc96afb113b4236ca097c138381c41d475bae1ca956c4f7ad32`
- DML (deterministic backfill, idempotent `ON CONFLICT DO NOTHING`): `20260823T090000Z_observatory_backfill_dml.sql`
  - SHA-256: `05ff23835df010da53edc6ff6940aedeb89cf2b0dc7c1d084eb788f480494aa3`
- Tables (8): `runs`(8), `run_events`(12), `run_gates`(1), `run_nodes`(2),
  `run_artifacts`(25), `run_checkpoints`(0), `run_edges`(0), `run_sources`(22).
- `run_kind`: `observed_real|simulated_fixture|golden_fixture|reconstructed_history`.
- `run_sources.source_system` (extended): `taskcontroller|gwc|github|repo_governance`.
  GitHub PR/issue/CI rows stored as `github`; evidence file as `repo_governance`.
- `run_artifacts.artifact_status`: `original|reconstructed|missing_unreconstructable`.
- Idempotent: `IF NOT EXISTS` DDL, event upsert key `UNIQUE(run_id, source_system, source_event_id)`,
  DML `ON CONFLICT DO NOTHING`. No `created_at` falsification.

## Offline dry-run (deterministic, truthful)
- Reconstruction timestamp (persisted, truthful): `2026-08-23T08:26:29.000Z`
  (from `.gwc/.../RECONSTRUCTION_META.json`; the actual governed-run activity time).
- Deterministic digest (normalized rows): `406658370a51a95f7e1da8a6e43caaf8cfd69171a511e036a86246a4373c0f26`
  (identical across two runs reading the same persisted timestamp).
- Real TypeScript type-check (compiler API, strict): PASS.
- RI: PASS (0). Idempotency: PASS (0 upsert conflicts). Separation: PASS (`observed_real=0`).
- Provenance: PASS — every artifact `source_refs` resolves to a `run_sources.source_ref`
  of the SAME run (including the `original` evidence-file artifact).
- **DML-vs-dry-run parity: PASS** — DML INSERT counts per table equal dry-run counts
  (runs 8, events 12, gates 1, nodes 2, sources 22, artifacts 25).

## Real evidence timestamps (no invented midnights)
- M3/M4 exact approved head `5e59c889039968f606d52906c5433a21a4751bd9` →
  CI run `32589399526` `Validate workspace = SUCCESS` @ `2026-08-22T17:59:37Z`.
- PR #79 merged `2026-08-22T18:06:04Z`; PR #76 merged `2026-08-21T13:59:19Z`;
  #77 `2026-08-21T18:38:13Z`; #78 `2026-08-22T16:55:25Z`.
- Issues #70–#75 created `2026-08-20T17:48:15Z` … `2026-08-20T18:49:17Z`.
- All `source_occurred_at/effective_at/occurred_at` bound to these; original
  `M3-M4-EVIDENCE.md` artifact uses PR #79 mergedAt, no fake midnight.

## Exact remote-apply command (validated against installed CLI — supabase 2.111.0)
The DML file lives under `supabase/migrations/`, so `supabase db push --linked
--include-all` applies BOTH DDL and DML in one pass. No separate `psql -f` step.
```
# from repo root (project config present), once:
supabase link --project-ref auswvdxoetufwiaxutib
# preview (no apply):
supabase db push --linked --dry-run
# approved apply (G6 bound): applies DDL + DML migrations
supabase db push --linked --include-all
```

## Reconstructed / missing (artifact status, not run_kind)
- `original`: 1 (`M3-M4-EVIDENCE.md` as `historical_evidence_file`; `reconstructed_at=NULL`)
- `reconstructed`: 23 (context/delivery/ci/alignment per run)
- `missing_unreconstructable`: 1 (M4 `gate_canonical_artifact` — no evidence; recorded, not invented)
- `observed_real` (live): 0

## Lifecycle status (per seq=10)
- G2 package: COMPLETE.
- G3 Draft PR #82: **OPEN / DRAFT** at exact head (this correction). Exact-head CI
  `Validate workspace #32628065467 = SUCCESS` was green; re-check CI for the new head.
- G4 exact-head merge authority: NOT done.
- G5 read-only merged-head status: NOT done.
- G6 remote DDL/DML: **STOP — blocked until exact G6 approval bound.**
- PR #81: untouched / unmerged (separate DRAFT UI run at `76670a5`).

## Exclusions honored
- No remote Supabase apply (G6 boundary) — STOP here.
- No `pre-prod -> main`, no deploy, no GWC mutation, no force-push/rewrite.
