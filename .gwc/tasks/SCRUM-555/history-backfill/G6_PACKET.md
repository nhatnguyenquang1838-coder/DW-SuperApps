# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · G6 APPROVAL PACKET

**STOP — human authority required before any remote apply.**

## Target
- Supabase project: `auswvdxoetufwiaxutib`, schema `public`. Current (verified): empty.
- DDL CREATES the 8-table schema.

## Migrations (both committed under `supabase/migrations/`, G6-gated)
- DDL: `20260823T080000Z_observatory_history.sql`
  - SHA-256: `ce91032e3e6b8b7f0674599c7a3653458641814abbbc15fa0fb4d527b9cf2f52`
- DML (deterministic, idempotent `ON CONFLICT DO NOTHING`): `20260823T090000Z_observatory_backfill_dml.sql`
  - SHA-256: `fcdcb295a1bae599f8ae135611766a754f7e4896de57c6d578bb8fef051c469b`
- Tables: `runs`(4), `run_events`(0), `run_gates`(3), `run_nodes`(3),
  `run_artifacts`(17), `run_checkpoints`(0), `run_edges`(0), `run_sources`(16).
- `run_kind`: `observed_real|simulated_fixture|golden_fixture|reconstructed_history`.
- `run_sources.source_system`: `taskcontroller|gwc|github|repo_governance`.
- `run_sources.source_kind` includes `repo_governance`.
- `run_nodes.gate_id` nullable FK (`ON DELETE SET NULL`); gates/nodes only where
  a real receipt exists (no invented gate/node rows).
- `runs` adds `scope_hash`, `base_sha`, `head_sha`, `merge_sha`.

## Offline dry-run (deterministic, truthful, schema-aware)
- Reconstruction timestamp (persisted, truthful): `2026-08-23T08:26:29.000Z`
  (from `RECONSTRUCTION_META.json`).
- Deterministic digest: `cc5938f8e49f81608fbc1006d090545f63b2dcaaf37a17a1f0ba8bd820d9b40e` (x2 identical).
- Real TS type-check (strict): PASS.
- **Schema-aware constraint check** (NOT NULL / CHECK enum / FK, mirrors DDL): PASS (0).
- RI: PASS (0). Idempotency: PASS (0 upsert conflicts). Separation: PASS (`observed_real=0`).
- Provenance: PASS — every artifact `source_refs` resolves to a same-run `run_sources.source_ref` (incl. original).
- **DML-vs-dry-run parity: PASS** (4/0/3/3/16/17).

## Run identities (exact receipts, NO invented ids)
- `DW-OBS-M0-20260821-R2` (reconstructed, R2 — not R1) · G2 `G2-DW-OBS-M0-20260821-R2`
- `G2-DW-OBS-M1-20260821-R1` (PR #77)
- `DW-OBS-M2-20260822-R1` (PR #78)
- `DW-OBS-M3M4-20260823-R1` (PR #79, one combined run) · G2 `G2-DW-OBS-M3M4-20260823-R1` · scope `aa5756f5dfc424ba`
- Golden fixtures (`run_scrum555_m0.json`, `run_gwc_durable_m0.json`) → `golden_fixture`
  **source rows** attached to the canonical M0 run, each preserving `source_run_id`.
  Their synthetic events are NOT backfilled as canonical `run_events` (events=0).

## SHA receipts (exact, from GitHub)
- M0 (#76): base `50a32124e826e6b4cfa36b0e315ab29d2672136a`, head `78171b5783278d680e3aef331fbb5b7fef4d63d0`, merged `2026-08-21T13:59:19Z`
- M1 (#77): base `79e6c485910f681ee0318ff7128eaa6971f8cc2a`, head `a94cf134c38c999daa63994b2b02d856078daee2`, merged `2026-08-21T18:38:13Z`
- M2 (#78): base `22d2d416169aaa8c60a84651d7f01694a193adb3`, head `4e4ba62b686f9aa49b932c412ec67b80767ed80d`, merged `2026-08-22T16:55:25Z`
- M3M4 (#79): base `edb91060017ea02685718a1fadf1dbb7acddbee7`, head `5e59c889039968f606d52906c5433a21a4751bd9`,
  scope `aa5756f5dfc424ba`, merge `a992fa4824db17434f6bdf8aabe8d6f435cc5767`, CI run `32589399526` @ `2026-08-22T17:59:37Z`
- Issues #70–#75 created `2026-08-20T17:48:15Z`…`18:49:17Z`.

## Artifact timestamps (per evidence type)
- context → issue createdAt · delivery → PR mergedAt · CI (M3M4 only) → CI run createdAt.
- Runs with NO CI receipt: `reconstructed_ci_evidence` recorded as `missing_unreconstructable`
  (PR/issue refs, NOT a fabricated CI artifact).
- Original `M3-M4-EVIDENCE.md`: `source_occurred_at=NULL` (file creation unknown),
  `effective_at`=merge time; full 64-hex SHA-256 stored.

## Exact remote-apply command (supabase 2.111.0)
DML lives under `supabase/migrations/` → `supabase db push --linked --include-all`
applies BOTH DDL + DML in one pass. No separate psql.
```
# from projects/dw-observation (project config present):
supabase link --project-ref auswvdxoetufwiaxutib
supabase db push --linked --include-all --dry-run     # preview
supabase db push --linked --include-all               # approved apply (G6 bound)
```

## Lifecycle (per seq=11)
- G2 package: COMPLETE. G3 Draft PR #82: OPEN/DRAFT at this head. Re-check CI for new SHA.
- G4 exact-head merge authority: NOT done. G5: NOT done. G6: STOP (no remote apply).
- PR #81: untouched/DRAFT @ `76670a5`.

## Exclusions
- No remote Supabase apply (G6 boundary). No pre-prod→main, no deploy, no GWC mutation, no force-push/rewrite.
