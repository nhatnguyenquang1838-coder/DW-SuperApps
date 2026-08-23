# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Reconstruction & Artifact Provenance

## Honesty rules applied (per seq=9)
- No fabrication or falsification of originals.
- No overwrite of `created_at` to pretend earlier existence. Ingestion timestamps
  stay truthful/current; historical semantics preserved in `source_occurred_at`.
- Insufficient-evidence runs recorded as `missing_unreconstructable`, not invented.

## Artifact counts (this backfill scope)

| Category | Count | Notes |
|----------|-------|-------|
| Original artifacts present in repo | 4 | 2 event streams (`run_scrum555_m0.json`, `run_gwc_durable_m0.json`) + 2 projections (`projection_scrum555_m0.json`, `projection_gwc_durable_m0.json`) |
| Reconstructed artifacts (run rows) | 6 | milestone delivery runs M0–M4 + M3M4, derived from PR/issue/evidence refs |
| Missing / unreconstructable | 0 | all 8 inventoried runs have sufficient authoritative evidence |
| Simulated fixtures included | 0 | Login Epic 10-run excluded by separation rule |

## Per-run provenance

| run_id | kind | basis | evidence_quality | confidence |
|--------|------|-------|------------------|------------|
| `DW-OBS-M0-20260821-R2` | observed_real | `fixtures/run_scrum555_m0.json` (7 events) | STRONG | HIGH |
| `run_dw_obs_m0_r2` | observed_real | `fixtures/run_gwc_durable_m0.json` (5 events) | STRONG | HIGH |
| `DW-OBS-M3M4-20260823-R1` | reconstructed_history | `M3-M4-EVIDENCE.md` + PR #79 | STRONG | HIGH |
| `DW-OBS-M0-20260821-R1` | reconstructed_history | PR #76 + issue #71 | STRONG | HIGH |
| `DW-OBS-M1-20260821-R1` | reconstructed_history | PR #77 + issue #72 | STRONG | HIGH |
| `DW-OBS-M2-20260822-R1` | reconstructed_history | PR #78 + issue #73 | STRONG | HIGH |
| `DW-OBS-M3-20260822-R1` | reconstructed_history | PR #79 + issue #74 | STRONG | HIGH |
| `DW-OBS-M4-20260822-R1` | reconstructed_history | PR #79 + issue #75 | STRONG | HIGH |

## Reconstruction fields written (schema)
For `reconstructed_history` rows:
- `artifact_status = 'reconstructed'`
- `original_artifact_present = false`
- `reconstructed_at = <current ISO timestamp>` (truthful)
- `reconstruction_basis`, `source_refs[]`, `reconstructed_by = 'TaskController/Hermes'`
- `confidence`, `evidence_quality` populated from evidence strength

For `observed_real` rows: `artifact_status = 'original'`, `original_artifact_present = true`,
`source_occurred_at` from fixture event timestamps (truthful historical time).

## Excluded
- Login Epic simulated 10-run fixtures: `simulated_fixture` — present ONLY on PR #81
  DRAFT branch, NOT on `pre-prod`. Deliberately excluded to honor real-vs-sim
  separation. Will be a separate backfill if/when that branch is merged with its
  own provenance.
