# R3 Closure Record — SCRUM-853 / VS1

**Run:** `SCRUM-853-DWO-V2-NATIVE-MAPPER-R3`
**Date:** 2026-11-10
**Executor:** DWA (DW Apps Agent)
**Status:** CLOSED — ACCEPTED

## 1. Scope

Versioned GWC v2 native source mapper for the DWO Observer application
(`projects/dw-observation/**`), per the accepted G1 plan and the confirmed
execution context:

- Task: SCRUM-853 (parent SCRUM-820)
- Repository: `nhatnguyenquang1838-coder/DW-SuperApps`
- Branch: `SCRUM-853-dwo-v2-native-mapper`
- Worktree: `D:/Projects/DW-SuperApps.worktrees/dwo-scrum853`
- Frozen GWC contract: `gwc/main@c93b722b2a611d805ada803920b92e205ec8cabc`
- DWO baseline: PR #130 HEAD `27be80874c34087ead4f98bc3afa6ee86274493a`
- Draft PR: #165

## 2. What was delivered

| Artifact | Path | Evidence |
|---|---|---|
| Versioned GWC v2 native mapper | `projects/dw-observation/lib/dwo/gwcV2SourceMapper.ts` | 117 lines, 207-commit diff |
| Golden/negative/compatibility tests | `projects/dw-observation/tests/unit/dwo/gwcV2SourceMapper.test.ts` | 8/8 vitest pass |
| Datasource config (runtime switch) | `projects/dw-observation/lib/dwo/dataSourceConfig.ts` | real/fixture switch, production guard |
| Datasource config tests | `projects/dw-observation/tests/unit/dwo/dataSourceConfig.test.ts` | 8/8 vitest pass |
| Fixture preview mode (delegates to config) | `projects/dw-observation/lib/dwo/fixturePreviewMode.ts` | updated to use dataSourceConfig |
| Draft PR | #165 | OPEN / DRAFT, base `integration/SCRUM-820-dwo-v2` |

## 3. Design decisions (binding)

1. **Exact source binding.** The mapper consumes the canonical v2
   `RunStateRecord` schema fields verbatim from
   `schemas/node-architect/universal-run/run-state-record.schema.json` at the
   frozen SHA. It does not scan `.gwc/tasks/*/g4/*.yaml` or infer approval state.
2. **Identity preserved.** `record_id`, `run_id`, `schema_id/version`,
   `lifecycle_profile`, `state_revision`, `predecessor_state_ref/digest`,
   `sequence`, `active_gate`, all 7 `gate_states`, and `terminal_state` are
   copied exactly.
3. **No fabrication.** `run_kind`, parent/child topology, sync health,
   qualification, authority, and timestamps are NOT inferred. `RunStateRecord
   v2` does not declare a run-kind field; the mapper emits `UNKNOWN` rather than
   guessing.
4. **Fail-closed.** Unsupported schema/version, lifecycle profile, `active_gate`,
   `terminal_state`, or a missing gate state each throw — no heuristic G0..G6.
5. **Read-only boundary.** `GWC_V2_MAPPER_CAPABILITIES` declares
   write/approve/deny/merge/deploy = false.

## 4. Verification evidence

| Check | Result |
|---|---|
| `vitest run tests/unit/dwo/gwcV2SourceMapper.test.ts` | 8/8 pass |
| `vitest run tests/unit/dwo/projectionContract.test.ts` | 27/27 pass (unchanged) |
| `vitest run tests/unit/dwo/` (full suite) | 818/819 pass; 1 flaky timeout (`t09c-adapter-dispatch`) passes in isolation at 6/6 |
| `pytest projects/dw-observation/tests/` | 157/157 pass, 4 subtests pass |
| `gh pr checks 165` | validate=pass, validate-worktree-policy=pass, typecheck-tests=pass |
| Exact-head diff vs base `458a5ed` | 2 files, 207 insertions, 0 deletions; only the two new files |

## 5. Boundaries respected

- No GWC repository, runtime, or publisher modifications.
- No remote database migrations, credentials, webhooks, or protected-branch merges.
- Legacy adapter (`GwcAdapter`, `TaskControllerAdapter`) and R5 UI untouched.
- `needs-gwc-v2-release-reconcile` label intentionally NOT applied — release
  reconciliation remains a separate tracking concern.

## 6. Open items

- None blocking. The Draft PR is open for review; merge is gated on the
  existing DW-SuperApps PR review process, not on GWC native admission.
