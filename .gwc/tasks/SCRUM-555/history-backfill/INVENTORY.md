# SCRUM-555 · DW-OBS-HIST-BACKFILL-R1 · Historical Run Inventory

**Run:** `DW-OBS-HIST-BACKFILL-R1`
**Branch:** `auto/SCRUM-555-observatory-history-backfill` (from `pre-prod@a992fa4824db17434f6bdf8aabe8d6f435cc5767`)
**Authority:** Controller seq=9 (TaskController/Hermes)
**Target Supabase project:** `auswvdxoetufwiaxutib` (currently `public` tables = `[]`, migrations = `[]`)
**G6 boundary:** prepare everything, **DO NOT remote apply** until exact G6 approval bound.

## Method

Inventory built ONLY from authoritative evidence:
- `.gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md` (run evidence)
- repo fixtures (`projects/dw-observation/fixtures/*.json`)
- GitHub PRs #76-#81, issues #70-#80, workflow runs (CI evidence)
- this canonical Slack thread (used only to confirm scope, NOT to infer run content)

NO run is inferred from chat prose. Login Epic simulated 10-run fixtures are
explicitly EXCLUDED from this backfill (they live only on the PR #81 branch,
which is a separate DRAFT run; blending them here would violate the
observed_real / simulated_fixture separation rule).

## Inventory of historical runs

| # | run_id | run_kind | source_system | evidence | events | notes |
|---|--------|----------|---------------|----------|--------|-------|
| 1 | `DW-OBS-M0-20260821-R2` | `observed_real` | taskcontroller | `fixtures/run_scrum555_m0.json` | 7 | real event stream; M0 canonical projection run |
| 2 | `run_dw_obs_m0_r2` | `observed_real` | gwc | `fixtures/run_gwc_durable_m0.json` | 5 | real event stream; run_started/gate_passed/node_started/node_completed/run_completed |
| 3 | `DW-OBS-M3M4-20260823-R1` | `reconstructed_history` | taskcontroller+gwc | `.gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md`, PR #79 | n/a (governance) | M3/M4 delivery run; authority `G2-DW-OBS-M3M4-20260823-R1`, scope `aa5756f5dfc424ba`, base `pre-prod@edb91060017ea02685718a1fadf1dbb7acddbee7`, nodes M3 #74 → M4 #75 |
| 4 | `DW-OBS-M0-20260821-R1` (M0 app source) | `reconstructed_history` | taskcontroller | PR #76 (merged), issue #71 | n/a | M0 milestone delivery; branch `auto/SCRUM-555-dw-observation-m0-r2` |
| 5 | `DW-OBS-M1-20260821-R1` | `reconstructed_history` | taskcontroller | PR #77 (merged), issue #72 | n/a | M1 historical runtime UI; branch `auto/SCRUM-555-dw-observation-m1-r1` |
| 6 | `DW-OBS-M2-20260822-R1` | `reconstructed_history` | taskcontroller | PR #78 (merged), issue #73 | n/a | M2 realtime projection delivery; branch `auto/SCRUM-555-dw-observation-m2-r1` |
| 7 | `DW-OBS-M3-20260822-R1` | `reconstructed_history` | taskcontroller | PR #79 (merged), issue #74 | n/a | M3 deterministic replay |
| 8 | `DW-OBS-M4-20260822-R1` | `reconstructed_history` | taskcontroller | PR #79 (merged), issue #75 | n/a | M4 review intelligence |

### run_kind classification rationale
- `observed_real`: runs with an actual event stream in repo fixtures (rows 1-2).
- `reconstructed_history`: milestone/governance delivery runs reconstructable from
  PR/issue/evidence artifacts, but with NO captured event stream in this repo
  snapshot. Marked `reconstructed` with `reconstruction_basis` = the PR/issue/evidence refs.
- `simulated_fixture`: Login Epic 10-run simulated fixtures — **EXCLUDED** from this
  backfill (separate PR #81 DRAFT run; do not blend).

## Artifacts available in repo (per-run raw data)
- `fixtures/run_scrum555_m0.json` → run 1 events
- `fixtures/run_gwc_durable_m0.json` → run 2 events
- `fixtures/projection_scrum555_m0.json` → run 1 projection (gates/nodes/anomalies)
- `fixtures/projection_gwc_durable_m0.json` → run 2 projection
- `sql/projection_events.sql` → existing M2 durable event-store DDL (reused as basis)

## Source references (provenance)
- GitHub PRs: #76 (M0), #77 (M1), #78 (M2), #79 (M3+M4), #81 (M5 DRAFT, NOT in this run)
- GitHub issues: #70 (parent), #71 (M0), #72 (M1), #73 (M2), #74 (M3), #75 (M4), #80 (M5 local-review/Supabase readiness)
- Workflow runs: `Validate workspace` CI green on all merged PRs; M5 DRAFT head CI `#32626391692 = SUCCESS` (PR #81, untouched).

## Counts (this backfill scope)
- `observed_real` runs: 2 (with event streams)
- `reconstructed_history` runs: 6 (milestone deliveries, no event stream in snapshot)
- `simulated_fixture` runs: 0 included (excluded by rule)
- Total runs inventoried: 8
- Original artifacts present in repo: 2 event streams + 2 projections + 1 evidence md
- Reconstructed artifacts to generate: milestone-run rows derived from PR/issue evidence
- Missing/unreconstructable: any run with insufficient evidence → recorded as `missing_unreconstructable`, not invented.

## Exclusions honored
- No remote Supabase apply (G6 boundary).
- PR #81 untouched / unmerged (separate DRAFT UI run at `76670a5`).
- No `pre-prod -> main`, no deploy, no GWC mutation, no force-push/rewrite.
