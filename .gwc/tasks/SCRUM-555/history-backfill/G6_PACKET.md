# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · G6 APPROVAL PACKET

**STOP — human authority required before any remote apply.**

## Target
- Supabase project: `auswvdxoetufwiaxutib`, schema `public`. Current: empty.
- DDL CREATES the 8-table schema.

## Migrations (both committed under `supabase/migrations/`, G6-gated)
- DDL: `20260823T080000Z_observatory_history.sql`
  - SHA-256: `ef880051d8fb7caf40005206d1200c3824509f8084ec771324866ee29500e185`
- DML (deterministic, idempotent `ON CONFLICT DO NOTHING`): `20260823T090000Z_observatory_backfill_dml.sql`
  - SHA-256: `df59a43c3cd6c6522a4b9ae71a148070c0c21c66682849878c6e3669ae3fa0ba`
- Tables: `runs`(4), `run_events`(0), `run_gates`(3), `run_nodes`(3),
  `run_artifacts`(17), `run_checkpoints`(0), `run_edges`(0), `run_sources`(23).
- `run_kind`: `observed_real|simulated_fixture|golden_fixture|reconstructed_history`.
- `run_sources.source_system`: `taskcontroller|gwc|github|repo_governance`.
- `run_sources.source_kind` includes `repo_governance` AND `controller_mailbox`.
- `run_nodes.gate_id` nullable FK. `runs` carries `scope_hash|base_sha|head_sha|merge_sha` (NO `scope_sha`).
- `runs.authority_ref` = approval_id (separate from `run_id`).

## Offline dry-run (deterministic, truthful, schema-aware)
- Reconstruction timestamp (persisted, truthful): `2026-08-23T08:26:29.000Z`.
- Deterministic digest: `ee63a3b9c926392ca45b5ea37073266ceb5afc52dc1e892a4c6c3f3efec4931d` (x2 identical).
- Real TS type-check (strict): PASS.
- **Schema-aware constraint check (NOT NULL/CHECK/FK, mirrors DDL): PASS (0).**
- RI: PASS. Idempotency: PASS. Separation (`observed_real=0`): PASS.
- Provenance: PASS (every artifact ref resolves to same-run `run_sources.source_ref`).
- **DML-vs-dry-run parity: PASS** (4/0/3/3/23/17).

## Run identities (exact receipts, NO invented ids)
- `DW-OBS-M0-20260821-R2` · approval `G2-DW-OBS-M0-20260821-R2`
- `DW-OBS-M1-20260821-R1` · approval `G2-DW-OBS-M1-20260821-R1`  (run_id ≠ approval_id)
- `DW-OBS-M2-20260822-R1` · approval `G2-DW-OBS-M2-20260822-R1`
- `DW-OBS-M3M4-20260823-R1` · approval `G2-DW-OBS-M3M4-20260823-R1` · scope `aa5756f5dfc424ba`
- Golden fixtures → `golden_fixture` source rows (preserve `source_run_id`); events NOT backfilled.

## Exact SHA receipts (terminal mailboxes #71-#73 + GitHub)
Linear chain (base → head → merge):
- M0 (#76): base `50a32124…`, head `78171b57…`, scope `5dc46c3b…`, merge `79e6c485…`, CI `32477448758` @ `2026-08-21T11:29:38Z`
- M1 (#77): base `79e6c485…`, head `a94cf13…`, scope `84f3326b…`, merge `22d2d416…`, CI `32513844239` @ `2026-08-21T18:32:09Z`
- M2 (#78): base `22d2d416…`, head `4e4ba62b…`, merge `edb91060…`, CI `32585204072` @ `2026-08-22T16:36:12Z`
- M3M4 (#79): base `edb91060…`, head `5e59c889…`, scope `aa5756f5…`, merge `a992fa4824db17434f6bdf8aabe8d6f435cc5767`, CI `32589399526` @ `2026-08-22T17:59:37Z`
- Issues #70–#75 created `2026-08-20T17:48:15Z`…`18:49:17Z`.

## Artifact timestamps (per evidence type)
- context → issue createdAt · delivery → PR mergedAt · CI → exact CI run createdAt (ALL 4 runs have real CI).
- Original `M3-M4-EVIDENCE.md`: `source_occurred_at=NULL`, `effective_at`=merge; full 64-hex SHA-256.

## Terminal-mailbox source refs
Each reconstructed run has a `controller_mailbox` `run_sources` row (source_kind) pointing to the
authoritative issue thread (#71 M0, #72 M1, #73 M2, #70 M3M4) carrying
`run_id/approval_id/scope_hash/head_sha/ci_run/merge_sha`. CI artifacts reference both the ci_run and mailbox sources.

## Exact remote-apply command (supabase 2.111.0)
DML lives under `supabase/migrations/` → `supabase db push --linked --include-all` applies BOTH.
No separate psql.
```
# from projects/dw-observation:
supabase link --project-ref auswvdxoetufwiaxutib
supabase db push --linked --include-all --dry-run     # preview
supabase db push --linked --include-all               # approved apply (G6 bound)
```

## Lifecycle (per seq=12)
- G2 package: COMPLETE. G3 Draft PR #82: OPEN/DRAFT at this head. Re-check CI for new SHA.
- G4 exact-head merge authority: NOT done. G5: NOT done. G6: STOP (no remote apply).
- PR #81: untouched/DRAFT @ `76670a5`.

## Exclusions
- No remote Supabase apply (G6 boundary). No pre-prod→main, no deploy, no GWC mutation, no force-push/rewrite.
