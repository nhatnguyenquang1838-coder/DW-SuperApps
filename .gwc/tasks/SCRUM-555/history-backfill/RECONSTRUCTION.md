# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Reconstruction & Artifact Provenance

## Honesty rules (per seq=9 + seq=10 corrections)
- No fabrication or falsification of originals. No fabricated CI run ids.
- No invented historical timestamps: every `source_occurred_at/effective_at/
  occurred_at` is bound to a real GitHub evidence timestamp (PR mergedAt, CI run
  createdAt, issue createdAt). Original `M3-M4-EVIDENCE.md` uses PR #79 mergedAt.
- `reconstructed_at` is the truthful, persisted governed-run timestamp
  (`2026-08-23T08:26:29.000Z`, from `RECONSTRUCTION_META.json`), used
  deterministically. Original artifacts use `reconstructed_at = NULL`
  (ingestion `created_at` carries current DB time).
- Event shape ≠ capture provenance: repo fixtures are golden, not live-captured.

## Classification
| run_id | run_kind | basis |
|--------|----------|-------|
| `DW-OBS-M0-20260821-R2` | `golden_fixture` | `fixtures/run_scrum555_m0.json` (PR #76 golden) |
| `run_dw_obs_m0_r2` | `golden_fixture` | `fixtures/run_gwc_durable_m0.json` (PR #76 golden) |
| `DW-OBS-M3M4-20260823-R1` | `reconstructed_history` | `M3-M4-EVIDENCE.md` + PR #79 @ `5e59c889…` |
| `DW-OBS-M0/M1/M2/M3-20260821/22-R1` | `reconstructed_history` | PR #76/#77/#78/#79 + issues #71–#74 |
| `DW-OBS-M4-20260822-R1` | `reconstructed_history` | PR #79 + issue #75 |

## REAL artifact inventory (not run_kind counts)
Deterministic digest: `406658370a51a95f7e1da8a6e43caaf8cfd69171a511e036a86246a4373c0f26`.

**By status (all runs):** original=1, reconstructed=23, missing_unreconstructable=1 (total 25).

**By run:**
| run_id | reconstructed | original | missing_unreconstructable |
|--------|---------------|---------|---------------------------|
| `DW-OBS-M3M4-20260823-R1` | 4 | 1 | 0 |
| `DW-OBS-M0-20260821-R1` | 4 | 0 | 0 |
| `DW-OBS-M1-20260821-R1` | 4 | 0 | 0 |
| `DW-OBS-M2-20260822-R1` | 4 | 0 | 0 |
| `DW-OBS-M3-20260822-R1` | 4 | 0 | 0 |
| `DW-OBS-M4-20260822-R1` | 3 | 0 | 1 |

**Artifact types:** `reconstructed_context_evidence` (issue), `reconstructed_delivery_record`
(PR merge), `reconstructed_ci_evidence` (CI run; M3M4 real run `32589399526` @ `2026-08-22T17:59:37Z`;
others infer from PR, `evidence_quality=PARTIAL`), `reconstructed_alignment_scope` (PR/issue),
`historical_evidence_file` (`M3-M4-EVIDENCE.md` as `original`), `gate_canonical_artifact`
(M4 `missing_unreconstructable`).

## run_sources provenance (22 rows, source_system reflects real system)
- 2 `golden_fixture` (fixtures, `source_system=taskcontroller|gwc`)
- Per reconstructed run: `github_pr` + `github_issue` + `reconstruction` (source_system=`github`/`repo_governance`)
- M3M4 adds `ci_run` (`github`, run `32589399526`) + `repo_governance` evidence-file row (path + digest)
- Each reconstructed run ≥1 source; each artifact ref resolves to a same-run `run_sources.source_ref`.

## Truthful timestamps (bound to evidence)
- M3/M4 CI: `32589399526` @ `2026-08-22T17:59:37Z` (head `5e59c889…`)
- PR merges: #76 `2026-08-21T13:59:19Z`, #77 `2026-08-21T18:38:13Z`, #78 `2026-08-22T16:55:25Z`, #79 `2026-08-22T18:06:04Z`
- Issues #70–#75: `2026-08-20T17:48:15Z` … `18:49:17Z`
- `reconstructed_at` (persisted): `2026-08-23T08:26:29.000Z`
