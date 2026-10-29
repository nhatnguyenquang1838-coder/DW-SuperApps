# DWO v2 Fixture Preview R1 — evidence report

## Scope and safety boundary

- Local-only preview over `DWO-UR-30-V1`; no database migration, production write, deployment, merge, or lifecycle mutation performed.
- Canonical Task/Run routes enter fixture mode only when `OBSERVATORY_DATA_SOURCE=fixture` **and** `NODE_ENV !== production`.
- Production/default mode was exercised with the fixture env unset: `/tasks` remained `Task source unavailable`, and all four canonical routes rendered without a `DEV FIXTURE` badge or fixture dataset.
- Fixture replay and qualification are read-only. `authorityGranted=false`; `projectionEventsMutated=false`; no LangGraph checkpoint is opened by the preview.

## F0 — inventory

`projects/dw-observation/dwo-v2/fixtures/DWO-UR-30-V1` contains **132 base-pack files** plus **29 qualification receipts**, for **161 total files** in the current tree. This reconciles the requested 132 count with the additive F3 qualification evidence; no parallel fixture pack was created.

| Pack component | Files / records |
|---|---:|
| `runs/*.yaml` | 30 |
| `events/projection-events.jsonl` | 1 file / 30 records |
| `tasks/task-relations.jsonl` | 1 file / 5 records |
| `evidence/qualification` | 29 receipts (DEV-RUN-020 intentionally has none) |
| Other evidence directories | execution 29, target 29, verification 16, closure 11, handoff 8, authority 1 |
| `expected/` | 5 golden outputs |
| `fixture-set.yaml` | 1 |

Existing reducer/replay/materializer path is reused: `fixtureSpec` → `materializeFixtureScenario` → `fixtureScenarioAdapter` → `UnifiedRunWorkspaceModel`; replay uses the shared `ReplaySession` reducer; qualification receipts remain a separate status axis.

## F1 — materialization and fail-closed cases

- All 30 catalog ids materialize and pass the materialization/evidence tests.
- `DEV-RUN-020`: incompatible, zero graph nodes/edges/history, no replay session; Task row uses `Projection Sync=DEGRADED`, `Semantic Qualification=UNKNOWN`, and no replay link.
- `DEV-RUN-022`: catalog gate `G5 / WAITING` is carried into the runtime node and displayed in Node Inspector without promotion to ACTIVE/PASSED.
- `DEV-RUN-030`: authority remains `NOT_REQUIRED`; the existing fixture contract test asserts it is not fabricated as UNKNOWN or DENIED.
- Root `taskRef` is sourced only from `tasks/task-relations.jsonl`; unclaimed child runs remain `null`, with no run-id inference.

## F2 — Fixture Lab replay

`/dev/fixtures` passes ordinal-ordered events for the selected scenario’s explicit materialized nodes to the client replay control, which uses the same `ReplaySession` as the rest of the DWO UI. Verified actions: arrive one event, reset, forward/backward, reconnect + catch-up, and CURRENT↔REPLAY. The `DEV-RUN-001` root scenario has four explicit self/direct-child snapshots; browser check observed `1/1` after first arrival, `4/4` after catch-up, then `REPLAY 2/4 SYNCHRONIZED`. No event or lifecycle state is invented; fixture snapshot rows without `event_type` are labeled `fixture_projection_snapshot`.

## F3 — qualification

- 29 synthetic receipts are parsed and verified against the Python contract’s canonical SHA-256 rules: exact subject digest, derived `qualification_id`, canonical `receipt_digest`, and bound `receipt_id`.
- Tampered subject, qualification id, receipt id, or invalid QUALIFIED evidence fails closed.
- The catalog’s expected split is **8 QUALIFIED / 21 UNKNOWN**; `DEV-RUN-020` has no receipt. Status is independent of projection sync and carries no authority/effect capability.
- The preview works without a LangGraph service/checkpointer; receipts are immutable fixture evidence.

## F4 — UI routes

With explicit local fixture mode, verified canonical paths are:

- `/tasks` → five fixture Task relations.
- `/tasks/TASK-CORE/runs` → eight root-run relations, per-run status axes, no replay link for DEV-RUN-020.
- `/runs/DEV-RUN-001` → fixture-backed workspace, Task context (`TASK-CORE`), qualification axis, DEV FIXTURE badge.
- `/runs/DEV-RUN-001/replay` → shared ReplayPane with five synchronized surfaces.

The `/dev/*` routes remain directly available for Fixture Lab and negative-fixture inspection. The production guard is enforced by `isLocalFixturePreview()` and was checked against a built production server with the env unset.

## F5 — verification evidence

- `npx vitest run`: **72 files passed / 1,014 tests passed**.
- `npx tsc --noEmit`: passed, no diagnostics.
- `npm run typecheck:tests:strict`: **0 errors** (baseline 86).
- `npx next build`: passed; all canonical and `/dev/*` routes registered.
- Browser capture: **8 required scenes** in this directory; individual SHA-256 values are in `MANIFEST-r1.sha256` and the scene index is `scenes-r1.json`.
- Playwright: `npx playwright test e2e/fixture-preview-r1.spec.ts --project=chromium` → **4 passed**; captures for Task-first screen, replay controls, G5 WAITING, and DEV-RUN-020 fail-closed are under `.preview-evidence/playwright-r1/`.
- Production-mode smoke: `/tasks`, `/tasks/TASK-CORE/runs`, `/runs/DEV-RUN-001`, and `/runs/DEV-RUN-001/replay` served without fixture badge/data. `/tasks` showed the real-source unavailable/fail-closed message.

## F6 — delivery

Source changes and the eight canonical screenshot artifacts are intended for the existing branch `integration/SCRUM-820-dwo-v2` and Draft PR #130. This report is evidence only; it does not authorize merge or deployment. The commit and remote PR head are recorded in the handoff after push.

## Residual risks / limitations

1. The source pack has one projection snapshot per run (30 rows / 30 runs). Individual run replay is therefore shallow; progressive replay is meaningful only when the scenario contains multiple explicitly materialized self/child snapshots. A richer multi-event fixture is needed to demonstrate a full lifecycle within one run.
2. Qualification receipts preserve their recorded immutable subject (`task_ref` is null in the current pack); the separate Task relation view does not rewrite or requalify that subject.
3. `next build` reports pre-existing warnings: invalid `next.config.mjs` key `devIndicator` and a missing `onOpenArtifact` dependency in `components/login-epic/RuntimeGraphCanvas.tsx:138`. Both are outside this fixture-preview scope; build succeeded.
4. Inventory reconciled: 132 base-pack files plus 29 qualification receipts = 161 total files; no parallel pack was created.
