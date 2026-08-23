# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Reconstruction & Artifact Provenance

## Honesty rules (seq=9 + seq=10 + seq=11)
- No fabrication of originals, run ids, CI receipts, or timestamps.
- No invented run identities: only exact GitHub receipts
  (`DW-OBS-M0-20260821-R2`, `G2-DW-OBS-M1-20260821-R1`, `DW-OBS-M2-20260822-R1`,
  `DW-OBS-M3M4-20260823-R1`). No R1/M3/M4 synthetic runs.
- Golden fixtures → `golden_fixture` **source rows** (preserving `source_run_id`),
  NOT separate runs; their synthetic events are NOT canonical `run_events` (events=0).
- All timestamps bound to real evidence (PR mergedAt, CI createdAt, issue createdAt).
- `reconstructed_at` = truthful persisted run ts; original artifact `reconstructed_at=NULL`.
- Schema-aware validation (NOT NULL/CHECK/FK) runs locally; no remote DB needed.

## Classification (4 runs, all reconstructed_history)
| run_id | authority | basis |
|--------|-----------|-------|
| `DW-OBS-M0-20260821-R2` | `G2-DW-OBS-M0-20260821-R2` | PR #76 + issue #71 (R2, not R1) |
| `G2-DW-OBS-M1-20260821-R1` | `G2-DW-OBS-M1-20260821-R1` | PR #77 + issue #72 |
| `DW-OBS-M2-20260822-R1` | (scope via PR #78) | PR #78 + issue #73 |
| `DW-OBS-M3M4-20260823-R1` | `G2-DW-OBS-M3M4-20260823-R1` | PR #79 + issue #70 (one combined run) |

Golden sources attached to canonical M0 run:
- `fixtures/run_scrum555_m0.json` (TaskController, `source_run_id=DW-OBS-M0-20260821-R2`)
- `fixtures/run_gwc_durable_m0.json` (GWC, `source_run_id=run_dw_obs_m0_r2`)

## SHA receipts (exact)
- M0 (#76): base `50a32124…`, head `78171b57…`, merge `2026-08-21T13:59:19Z`
- M1 (#77): base `79e6c485…`, head `a94cf134…`, merge `2026-08-21T18:38:13Z`
- M2 (#78): base `22d2d416…`, head `4e4ba62b…`, merge `2026-08-22T16:55:25Z`
- M3M4 (#79): base `edb91060…`, head `5e59c889…`, scope `aa5756f5dfc424ba`,
  merge `a992fa4824db17434f6bdf8aabe8d6f435cc5767`, CI run `32589399526` @ `2026-08-22T17:59:37Z`

## REAL artifact inventory (counts)
Deterministic digest: `cc5938f8e49f81608fbc1006d090545f63b2dcaaf37a17a1f0ba8bd820d9b40e`.

**By status (all runs):** original=1, reconstructed=13, missing_unreconstructable=3 (total 17).
- `original`: `M3-M4-EVIDENCE.md` (full 64-hex SHA-256, `source_occurred_at=NULL`, `effective_at`=merge).
- `reconstructed`: context(issue ts) / delivery(PR merge ts) / CI(real, M3M4 only) / alignment(PR merge ts).
- `missing_unreconstructable`: CI receipt for M0/M1/M2 (no CI run captured; PR/issue refs prove delivery).

**By run:**
| run_id | reconstructed | original | missing_unreconstructable |
|--------|---------------|---------|---------------------------|
| `DW-OBS-M0-20260821-R2` | 3 | 0 | 1 |
| `G2-DW-OBS-M1-20260821-R1` | 3 | 0 | 1 |
| `DW-OBS-M2-20260822-R1` | 3 | 0 | 1 |
| `DW-OBS-M3M4-20260823-R1` | 4 | 1 | 0 |

## Gates / Nodes (only where receipt exists)
- `run_gates` (3): `G2-DW-OBS-M0-20260821-R2`, `G2-DW-OBS-M1-20260821-R1`, `G2-DW-OBS-M3M4-20260823-R1`.
- `run_nodes` (3): M0 node `71` (gate `G2-DW-OBS-M0-20260821-R2`), M3M4 nodes `74`,`75` (gate `G2-DW-OBS-M3M4-20260823-R1`).
- `run_nodes.gate_id` is nullable FK; node `71` binds its proven gate. No invented rows.

## run_sources provenance (16 rows)
- 2 `golden_fixture` (M0 canonical run, preserving each source_run_id)
- Per reconstructed run: `github_pr` + `github_issue` + `reconstruction`
- M3M4 adds `ci_run` (`github`) + `repo_governance` evidence-file row (path + full 64-hex digest)
- Each reconstructed run ≥1 source; each artifact ref resolves to a same-run `run_sources.source_ref`.

## Validation (offline, before G3 PASS)
- Real TS type-check (strict): PASS
- Deterministic digest (x2 identical): PASS
- Schema-aware constraint check (NOT NULL/CHECK/FK): PASS (0)
- RI / idempotency / separation (`observed_real=0`): PASS
- Provenance: PASS (0)
- DML-vs-dry-run parity: PASS (4/0/3/3/16/17)
