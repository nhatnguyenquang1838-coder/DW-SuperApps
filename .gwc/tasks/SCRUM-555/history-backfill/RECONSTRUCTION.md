# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Reconstruction & Artifact Provenance

## Honesty rules (per seq=9 + seq=9 correction)
- No fabrication or falsification of originals.
- No overwrite of `created_at` to pretend earlier existence. Ingestion timestamps
  stay truthful/current; historical semantics preserved in `source_occurred_at`.
- Insufficient-evidence runs recorded as `missing_unreconstructable`, not invented.
- **Event shape ≠ capture provenance**: repo fixtures are golden, not live-captured.

## Classification (corrected)
| run_id | run_kind | basis |
|--------|----------|-------|
| `DW-OBS-M0-202palette...` → `DW-OBS-M0-20260821-R2` | `golden_fixture` | `fixtures/run_scrum555_m0.json` (PR #76: "Golden fixtures + replay tests") |
| `run_dw_obs_m0_r2` | `golden_fixture` | `fixtures/run_gwc_durable_m0.json` (PR #76 golden) |
| `DW-OBS-M3M4-20260823-R1` | `reconstructed_history` | `M3-M4-EVIDENCE.md` + PR #79 |
| `DW-OBS-M0-20260821-R1` | `reconstructed_history` | PR #76 + issue #71 |
| `DW-OBS-M1-20260821-R1` | `reconstructed_history` | PR #77 + issue #72 |
| `DW-OBS-M2-20260822-R1` | `reconstructed_history` | PR #78 + issue #73 |
| `DW-OBS-M3-20260822-R1` | `reconstructed_history` | PR #79 + issue #74 |
| `DW-OBS-M4-20260822-R1` | `reconstructed_history` | PR #79 + issue #75 |

## Artifact counts (corrected)
| Category | Count | Notes |
|----------|-------|-------|
| `observed_real` (live capture) | **0** | no source-ledger receipt / export / ingestion receipt produced |
| `golden_fixture` | 2 | repo event-stream fixtures (PR #76 contract) |
| `reconstructed_history` | 6 | milestone delivery runs from PR/issue/CI evidence |
| `simulated_fixture` (Login Epic 10-run) | 0 | excluded (separate PR #81 DRAFT run) |
| Missing / unreconstructable | 0 | all 8 runs have sufficient authoritative evidence |
| Original ledger present | 0 | no live-capture original exists in this repo snapshot |

## run_sources provenance fields (added per correction #5)
- `source_kind`: `live_capture | golden_fixture | github_pr | github_issue | ci_run | gwc_artifact | reconstruction`
- `capture_provenance_verified`: BOOLEAN (false for golden fixtures)
- `source_ref`: TEXT
- `source_digest`: TEXT (optional)

Golden fixtures → `source_kind='golden_fixture'`, `capture_provenance_verified=false`.
Reconstructed runs → `source_kind='reconstruction'` / `github_pr` / `github_issue`.

## Truthful timestamps
- `reconstructed_at` / ingestion `created_at` = current (truthful).
- `source_occurred_at` / `effective_at` = historical event time where known.
- NO backdated `created_at`.
