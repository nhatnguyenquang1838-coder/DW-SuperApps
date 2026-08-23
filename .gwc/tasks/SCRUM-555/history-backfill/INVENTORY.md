# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Historical Run Inventory

**Run:** `DW-OBS-HIST-BACKFILL-R1`
**Branch:** `auto/SCRUM-555-observatory-history-backfill` (from `pre-prod@a992fa4824db17434f6bdf8aabe8d6f435cc5767`)
**Authority:** Controller seq=9 (+ seq=9 correction on classification)
**Target Supabase project:** `auswvdxoetufwiaxutib` (currently `public` tables = `[]`, migrations = `[]`)
**G6 boundary:** prepare everything, **DO NOT remote apply** until exact G6 approval bound.

## Method
Inventory built ONLY from authoritative evidence:
- `.gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md`
- repo fixtures (`projects/dw-observation/fixtures/*.json`)
- GitHub PRs #76-#81, issues #70-#80, workflow runs
- this canonical Slack thread (scope confirmation only, NOT run inference)

NO run inferred from chat prose.

## seq=9 correction applied (provenance, not shape)
PR #76 contract: fixtures are *"Golden fixtures + replay tests (reproducible, no network)"*.
Event-array presence ≠ live-capture provenance. Therefore:
- `DW-OBS-M0-20260821-R2` and `run_dw_obs_m0_r2` are classified **`golden_fixture`**
  (NOT `observed_real`). No source ledger location / immutable export / ingestion
  receipt was produced proving live capture.
- The real M0 development/governance run is represented separately as
  **`reconstructed_history`** from PR #76 / issue #71 / CI / approvals.
- Login Epic simulated 10-run fixtures: **EXCLUDED** (only on PR #81 DRAFT branch).

## Inventory

| # | run_id | run_kind | source | evidence | events |
|---|--------|----------|--------|----------|--------|
| 1 | `DW-OBS-M0-20260821-R2` | `golden_fixture` | - | `fixtures/run_scrum555_m0.json` (PR #76 golden) | 7 |
| 2 | `run_dw_obs_m0_r2` | `golden_fixture` | - | `fixtures/run_gwc_durable_m0.json` (PR #76 golden) | 5 |
| 3 | `DW-OBS-M3M4-20260823-R1` | `reconstructed_history` | - | `M3-M4-EVIDENCE.md`, PR #79 | n/a |
| 4 | `DW-OBS-M0-20260821-R1` | `reconstructed_history` | PR #76, issue #71 | M0 app source | n/a |
| 5 | `DW-OBS-M1-20260821-R1` | `reconstructed_history` | PR #77, issue #72 | historical UI | n/a |
| 6 | `DW-OBS-M2-20260822-R1` | `reconstructed_history` | PR #78, issue #73 | realtime projection | n/a |
| 7 | `DW-OBS-M3-20260822-R1` | `reconstructed_history` | PR #79, issue #74 | deterministic replay | n/a |
| 8 | `DW-OBS-M4-20260822-R1` | `reconstructed_history` | PR #79, issue #75 | review intelligence | n/a |

## Counts (corrected)
- `golden_fixture`: 2
- `reconstructed_history`: 6
- `observed_real`: **0** (no live-capture provenance found)
- `simulated_fixture` (Login Epic 10-run): 0 included (excluded)
- Total runs: 8

## Supporting sources (run_sources)
- 2 `golden_fixture` source rows, `capture_provenance_verified = false`,
  `source_ref` = fixture path, evidence = PR #76 contract.
- 6 `reconstruction` source rows (one per reconstructed run) from PR/issue refs.

## Exclusions honored
- No remote Supabase apply (G6 boundary).
- PR #81 untouched / unmerged (separate DRAFT UI run at `76670a5`).
- No `pre-prod -> main`, no deploy, no GWC mutation, no force-push/rewrite.
