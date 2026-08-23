# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Reconstruction & Artifact Provenance

## Honesty rules (seq=9/10/11/12)
- No fabrication of originals, run ids, CI receipts, or timestamps.
- Only exact GitHub receipts + terminal-mailbox (#71–#73) identities.
- `run_id` ≠ `approval_id` (kept separate; `authority_ref` = approval_id).
- Golden fixtures → `golden_fixture` source rows (preserve `source_run_id`); events NOT backfilled (events=0).
- All timestamps bound to real evidence. `reconstructed_at` truthful persisted; original `reconstructed_at=NULL`.
- CI receipts exist for ALL four runs (no `missing_unreconstructable` CI).
- Schema-aware validation (NOT NULL/CHECK/FK) runs locally.

## Classification (4 runs, all reconstructed_history)
| run_id | approval_id | basis |
|--------|-------------|-------|
| `DW-OBS-M0-20260821-R2` | `G2-DW-OBS-M0-20260821-R2` | PR #76 + mailbox #71 |
| `DW-OBS-M1-20260821-R1` | `G2-DW-OBS-M1-20260821-R1` | PR #77 + mailbox #72 |
| `DW-OBS-M2-20260822-R1` | `G2-DW-OBS-M2-20260822-R1` | PR #78 + mailbox #73 |
| `DW-OBS-M3M4-20260823-R1` | `G2-DW-OBS-M3M4-20260823-R1` | PR #79 + mailbox #70 |

## Linear SHA chain (base → head → merge) + CI + scope
- M0: base `50a32124…`, head `78171b57…`, scope `5dc46c3b8bc69b89fde4edd958bf7a398974d806649a277d52789e62ed85116f`, merge `79e6c485…`, CI `32477448758` @ `2026-08-21T11:29:38Z`
- M1: base `79e6c485…`, head `a94cf13…`, scope `84f3326b8126d700cbff3aff84c9cf901aae31ba4b55081f80820c46f2e718d1`, merge `22d2d416…`, CI `32513844239` @ `2026-08-21T18:32:09Z`
- M2: base `22d2d416…`, head `4e4ba62b…`, merge `edb91060…`, CI `32585204072` @ `2026-08-22T16:36:12Z`
- M3M4: base `edb91060…`, head `5e59c889…`, scope `aa5756f5dfc424ba`, merge `a992fa4824db17434f6bdf8aabe8d6f435cc5767`, CI `32589399526` @ `2026-08-22T17:59:37Z`

## REAL artifact inventory
Deterministic digest: `ee63a3b9c926392ca45b5ea37073266ceb5afc52dc1e892a4c6c3f3efec4931d`.

**By status (all runs):** original=1, reconstructed=16, missing_unreconstructable=0 (total 17).
- `original`: `M3-M4-EVIDENCE.md` (full 64-hex SHA-256, `source_occurred_at=NULL`, `effective_at`=merge).
- `reconstructed=16`: per run context(issue ts)/delivery(PR merge ts)/CI(exact CI run ts, ALL 4)/alignment(PR merge ts) = 4 each.
- No CI `missing_unreconstructable` (all four CI receipts proven).

**By run:**
| run_id | reconstructed | original | missing |
|--------|---------------|---------|---------|
| `DW-OBS-M0-20260821-R2` | 4 | 0 | 0 |
| `DW-OBS-M1-20260821-R1` | 4 | 0 | 0 |
| `DW-OBS-M2-20260822-R1` | 4 | 0 | 0 |
| `DW-OBS-M3M4-20260823-R1` | 4 | 1 | 0 |

## Gates / Nodes (only where receipt exists)
- `run_gates` (3): `G2-DW-OBS-M0-20260821-R2`, `G2-DW-OBS-M1-20260821-R1`, `G2-DW-OBS-M3M4-20260823-R1`.
- `run_nodes` (3): M0 node `71`, M3M4 nodes `74`,`75`. `run_nodes.gate_id` nullable FK.

## run_sources provenance (23 rows)
Per run (×4): `github_pr` + `github_issue`(generic, issue-created ts) + `ci_run`(real) + `reconstruction` + `controller_mailbox`(binding the EXACT canonical receipt comment, `source_system='github'`, `occurred_at`=proven comment ts):
- M0: `github:issue/71#issuecomment-5370838035` (M0 TERMINAL, `2026-08-21T14:03:22Z`)
- M1: `github:issue/72#issuecomment-5370849202` (`2026-08-21T14:04:08Z`)
- M2: `github:issue/73#issuecomment-5373867605` (`2026-08-21T18:42:23Z`)
- M3M4: `github:issue/70#issuecomment-5381850075` (`2026-08-22T18:08:14Z`)
- M3M4 adds `repo_governance` evidence-file row (path + full 64-hex digest).
- 2 `golden_fixture` (M0 canonical run, preserving each `source_run_id`).
Total = 5×3 + 6 + 2 = 23.

## Validation (offline, before G3 PASS)
- Real TS type-check (strict): PASS
- Deterministic digest (x2 identical): PASS
- Schema-aware constraint check (NOT NULL/CHECK/FK): PASS (0)
- RI / idempotency / separation (`observed_real=0`): PASS
- Provenance: PASS (0)
- DML-vs-dry-run parity: PASS (4/0/3/3/23/17)
