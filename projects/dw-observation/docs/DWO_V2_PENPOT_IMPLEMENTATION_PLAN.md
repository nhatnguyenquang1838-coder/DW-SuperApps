# DWO v2 Penpot Implementation Plan

Status: READY TO EXECUTE
Target branch: integration/SCRUM-820-dwo-v2
Write scope: projects/dw-observation/**

## Execution DAG

```text
T01 Tokens/Shell
 ├─> T05 Unified Workspace
 ├─> T08 Dashboard
 └─> T10 Storybook

T02 Canonical Task Gateway
 └─> T03 Task->Run Hydration
      └─> T08 Dashboard

T04 Unified Runtime Model + Adapters
 ├─> T05 Unified Workspace
 ├─> T06 Replay
 ├─> T07 Next Flow
 └─> T09 Fixture Materializer

T05 Unified Workspace
 ├─> T06 Replay
 ├─> T07 Next Flow
 ├─> T09 Fixture Materializer
 └─> T10 Storybook

T06 Replay ─┐
T07 NextFlow├─> T11 Playwright
T08 Dashboard
T09 Fixtures┘

T10 Storybook ─> T12 Acceptance
T11 Playwright ─> T12 Acceptance
```

## T01 — Materialize Penpot tokens and application shell

Goal:
Replace per-screen hardcoded visual styling with semantic DWO tokens and a reusable shell.

Targets:
- app/globals.css
- tailwind.config.*
- components/dwo/TopNavigation.tsx
- components/dwo/MetricCard.tsx
- components/dwo/StatusPill.tsx
- components/dwo/WorkspaceShell.tsx

Acceptance:
- Penpot DWO/Core color/spacing/radius semantics mapped once
- Dashboard/Tasks/TaskRuns/Workspace share navigation shell
- no new raw hex values in page-level components
- current app still typechecks and existing tests pass

Depends on: none

## T02 — Canonical Task read gateway

Goal:
Remove production dependency on taskFixtures from /tasks.

Create:
- lib/taskRead.ts
- lib/taskTypes.ts

Modify:
- app/tasks/page.tsx

Contract:
- mock/dev path may use fixtures behind explicit adapter
- real path must resolve canonical task/index source
- unresolved/unavailable remains explicit

Acceptance:
- /tasks has no direct import from taskFixtures
- real mode has zero fixture fallback
- UNKNOWN/CONFLICT/UNAVAILABLE test coverage

Depends on: none

## T03 — Source-backed Task -> Root Run hydration

Goal:
Remove listRuns("mock") from /tasks/[taskId]/runs production flow.

Modify:
- app/tasks/[taskId]/runs/page.tsx
- TaskRunIndexV2 gateway/resolver
- server run summary read path

Acceptance:
- same selected data source resolves both mapping and run summaries
- relation revision/digest surfaced
- absent run metadata stays UNKNOWN
- same-revision relation conflict fails closed
- no run-id inference

Depends on: T02

## T04 — UnifiedRuntimeModel and adapters

Goal:
Unify login-epic, Node Architect and real runtime models before UI refactor.

Create:
- lib/runtime/unifiedRuntime.ts
- lib/runtime/adapters/realRuntimeAdapter.ts
- lib/runtime/adapters/loginAuthScenarioAdapter.ts
- lib/runtime/adapters/nodeArchitectScenarioAdapter.ts
- lib/runtime/adapters/fixtureScenarioAdapter.ts

Refactor/reuse:
- lib/loginEpicRuntimeGraph.ts
- lib/simRun.ts

Acceptance:
- renderer receives one normalized model
- node-owned artifacts/files/history/checkpoints preserved
- hierarchy and dependency represented separately
- adapter tests deterministic
- no React imports in reducer/adapter modules

Depends on: none

## T05 — Build UnifiedRunWorkspace

Goal:
Replace vertical Run Detail and separate dev simulation shells with the Penpot workspace.

Create/refactor:
- components/dwo/workspace/UnifiedRunWorkspace.tsx
- ScenarioRunRail.tsx
- RunHierarchy.tsx
- RuntimeGraphCanvas.tsx
- NodeInspector.tsx
- inspector/*
- RuntimePlayer.tsx

Reuse:
- login-epic RuntimeGraphCanvas mechanics
- GateClusterNode
- RuntimeNodeCard
- RuntimeEdge
- MiniMap
- Node Architect inspector semantics

Modify:
- app/runs/[runId]/page.tsx
- dev simulation entry points to render same workspace

Acceptance:
- Penpot regions present
- Login Auth and Node Architect scenarios use same component tree
- Tree and dependency graph visibly distinct
- current selected node drives Inspector
- Follow cursor and layout controls preserved
- no bespoke fixture workspace

Depends on: T01, T04

## T06 — Real Replay reducer and same-shell replay mode

Goal:
Wire canonical durable replay and remove separate Replay UI.

Create:
- lib/runtime/replay.ts
- components/dwo/workspace/ReplayContextBar.tsx

Modify:
- app/runs/[runId]/page.tsx
- app/runs/[runId]/replay/page.tsx
- serverRunRead as required

Behavior:
- /runs/:id?mode=replay&seq=N renders UnifiedRunWorkspace
- legacy /replay route redirects/deep-links only
- reducer consumes events <= seq only

Acceptance:
- real replay no longer returns []
- no future/live data visible in replay
- invalid/unavailable sequence fails closed
- replay snapshot unit tests cover beginning/middle/end/conflict

Depends on: T04, T05

## T07 — Source-backed Next Flow

Goal:
Implement the Penpot Next Flow panel from runtime evidence.

Create:
- lib/runtime/nextFlow.ts
- components/dwo/workspace/NextFlowPanel.tsx

Acceptance:
- current/next/reason/blocker fields
- RESOLVED/BLOCKED/UNKNOWN/CONFLICT
- no visual adjacency inference
- replay computes as-of selected sequence
- unit tests for missing/conflicting evidence

Depends on: T04, T05

## T08 — Operational Dashboard

Goal:
Implement Penpot Dashboard using canonical projections.

Create:
- lib/dashboard/readDashboardProjection.ts
- components/dwo/dashboard/*

Modify/create:
- app/dashboard/page.tsx
- global navigation

Acceptance:
- active/waiting/blocked/completed
- unresolved/anomaly/authority/degraded metrics
- recent durable activity
- needs attention list
- Task -> Root Run -> Workspace drilldown
- unavailable source renders explicit unavailable metric, not zero

Depends on: T01, T02, T03

## T09 — 30 executable fixture scenarios

Goal:
Upgrade DWO-UR-30-V1 from catalog metadata to complete simulated workspaces.

Create:
- lib/dwo/materializeFixtureScenario.ts
- scenario data/builders as needed

Modify:
- lib/dwo/fixtureSpec.ts
- app/dev/fixtures/page.tsx
- add dev route/deep-link for selected scenario or use /runs/DEV-RUN-xxx?scenario=...

Acceptance:
- 30/30 IDs materialize UnifiedRunWorkspaceModel
- every card opens a full workspace
- timeline/replay available where scenario declares history
- DEV-RUN-020 relation conflict -> FAIL-CLOSED
- invariant test rejects incomplete scenario definitions

Depends on: T04, T05, T07

## T10 — Storybook executable design contract

Goal:
Encode Penpot states as isolated executable stories.

Add compatible Storybook 8.6.x setup.

Stories:
- StatusPill
- RuntimeNodeCard
- NextFlowPanel
- NodeInspector
- RuntimePlayer
- UnifiedRunWorkspace
- Dashboard

Workspace stories:
- LoginAuthSimulated
- NodeArchitectSimulated
- LiveReal
- Replay
- Degraded
- RelationConflict

Acceptance:
- CSF3 typed stories
- args drive visual states
- play functions cover key interactions
- no network dependency for deterministic stories
- storybook build succeeds in CI/local verification

Depends on: T01, T05, T07, T08

## T11 — Playwright navigation + visual regression

Goal:
Protect the Penpot-to-code contract in-browser.

Add:
- @playwright/test
- playwright.config.ts
- e2e/dwo-navigation.spec.ts
- e2e/dwo-visual.spec.ts
- deterministic screenshot CSS if required

Acceptance:
- URL assertions for full navigation chain
- screenshots for 6 canonical surfaces/states
- animations disabled for screenshots
- semantic assertions for mode/source/fail-closed in addition to screenshots
- DEV-RUN-020 verified as conflict, not just visually red

Depends on: T05, T06, T07, T08, T09

## T12 — Acceptance and PR readiness

Goal:
Close the Penpot implementation round with evidence.

Required evidence:
- typecheck
- Vitest
- Storybook build
- Playwright navigation
- Playwright screenshots
- source-backed real-mode tests
- replay isolation tests
- fixture 30/30 invariant

Acceptance:
- update PR #130 with exact command/result evidence
- keep Draft if any acceptance condition remains open
- no merge/main/deploy action in this task

Depends on: T06, T07, T08, T09, T10, T11

## Recommended execution order

1. T01 + T02 + T04
2. T03
3. T05
4. T06 + T07
5. T08 + T09
6. T10
7. T11
8. T12

## Guardrails

- Do not upgrade Next.js/React as part of this work.
- Do not replace React Flow unless a concrete blocker is proven.
- Do not create a second Replay shell.
- Do not create a fixture-only runtime component tree.
- Do not make dev fixtures visible in primary production navigation.
- Do not infer missing runtime/task truth.
- Do not merge/deploy from this plan.
