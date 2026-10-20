# DWO v2 Penpot-to-Code Technical Specification

Status: IMPLEMENTATION INPUT
Branch: integration/SCRUM-820-dwo-v2
Scope: projects/dw-observation/**
Canonical visual source: Penpot file "DWO v2 — Canonical UX"
Governance mode: TASKCONTROLLER_MVP · non-GWC

## 1. Purpose

Translate the approved Penpot interaction model into a production-equivalent frontend architecture without creating a separate fixture-only UI.

Canonical IA:

- /dashboard
- /tasks
- /tasks/[taskId]/runs
- /runs/[runId]
- /dev/fixtures

Replay is a mode of /runs/[runId], not a second product shell.

## 2. Current implementation baseline

Current application stack:

- Next.js 14.2.5 App Router
- React 18.3.1
- @xyflow/react 12.3.5
- Tailwind 3.4.6
- Vitest 2.0.5
- Supabase JS 2.45.x

Current code already contains two useful simulation implementations:

1. login-epic simulation
   - React Flow graph
   - gate clusters
   - runtime node cards
   - route/fanout edges
   - follow cursor
   - LR/TD + stack/grid/group
   - node-owned files/artifacts/runbook/history/checkpoints
   - runtime player

2. Node Architect simulation
   - node-centric inspector semantics
   - node type/family/authority/source/maturity/declared gates
   - artifact/runbook/history/checkpoint ownership

These must converge into one runtime model and one workspace shell.

## 3. Source-of-truth hierarchy

Semantic authority:

1. durable runtime/task relation sources
2. canonical server read contracts
3. Penpot interaction/visual contract
4. Storybook executable state contract
5. Playwright visual/navigation regression

Rules:

- UI never infers missing truth.
- Real mode never falls back to fixtures.
- Same-revision conflicts fail closed.
- UNKNOWN stays explicit.
- hierarchy and dependency are separate concepts.
- Replay cannot consume future or live state.
- Fixture simulations must reuse the same reducer/view-model/render path as the production workspace.

## 4. Route contract

### /dashboard

Operational entry point. Source-backed aggregates only.

Required states:
- active/running
- waiting
- blocked
- completed
- anomalies/unresolved
- authority waits
- degraded/unavailable
- recent durable activity
- tasks needing attention

No fixture-only counts in production mode.

### /tasks

Canonical task index.

Must not import TASK_META/getTaskRootRuns from taskFixtures in the production path.

Required row model:

```ts
interface TaskSummary {
  taskRef: string;
  title: string | null;
  domain: string | null;
  rootRunCount: number | null;
  latestRunId: string | null;
  latestState: string | null;
  relationRevision: number | null;
  status: "RESOLVED" | "UNKNOWN_UNRESOLVED" | "CONFLICT" | "UNAVAILABLE";
}
```

### /tasks/[taskId]/runs

Summary/navigation surface only.

Required model:

```ts
interface TaskRunSummary {
  runId: string;
  status: string;
  sourceSystem: string | null;
  lane: string | null;
  startedAt: string | null;
  lifecycleProgress: { completed: number; total: number } | null;
  anomalyCount: number | null;
  relationRevision: number | null;
}
```

The page must resolve TaskRunIndexV2 through a source-backed gateway and hydrate runs through the same selected data source. It must not use listRuns("mock") in real mode.

### /runs/[runId]

Single canonical runtime workspace.

Search params:

```text
mode=live|replay
seq=<durable sequence>
scenario=<optional dev scenario id>
```

For Next.js 14.2.5, keep route prop signatures compatible with the installed framework version. Do not copy newer async params/searchParams signatures from newer Next.js docs without upgrading the framework.

Legacy /runs/[runId]/replay may remain only as a redirect/deep-link compatibility route to:
```text
/runs/[runId]?mode=replay&seq=<resolved sequence>
```

It must not render a second product UI.

## 5. Unified runtime domain model

Create a renderer-neutral model shared by real runtime data and simulations.

```ts
type WorkspaceMode = "LIVE" | "REPLAY" | "SIMULATED";

type RuntimeNodeState =
  | "DONE"
  | "ACTIVE"
  | "FUTURE"
  | "BLOCKED"
  | "WAITING"
  | "UNKNOWN";

interface UnifiedRuntimeNode {
  id: string;
  gateId: string | null;
  title: string;
  family: string | null;
  nodeType: string | null;
  authorityBoundary: string | null;
  sourceStatus: string | null;
  maturity: string | null;
  declaredGates: string[];
  purpose: string | null;
  fileReads: string[];
  fileWrites: string[];
  artifacts: string[];
  runbook: string[];
  taskControllerHistory: unknown[];
  executorHistory: unknown[];
  checkpoints: unknown[];
}

interface UnifiedRuntimeEdge {
  id: string;
  source: string;
  target: string;
  kind: "DEPENDENCY" | "ROUTE" | "FANOUT";
  state: "SATISFIED" | "BLOCKING" | "UNKNOWN";
}

interface UnifiedRunWorkspaceModel {
  runId: string;
  taskRef: string | null;
  mode: WorkspaceMode;
  status: string;
  hierarchy: unknown;
  nodes: UnifiedRuntimeNode[];
  edges: UnifiedRuntimeEdge[];
  orderedSteps: Array<{ nodeId: string; sequence: number }>;
  currentSequence: number | null;
  canonicalHistoryAvailable: boolean;
  projectionStatus: string;
  sourceDigest: string | null;
}
```

Adapters:

```text
RealRuntimeAdapter
LoginAuthScenarioAdapter
NodeArchitectScenarioAdapter
FixtureScenarioAdapter
           ↓
UnifiedRunWorkspaceModel
           ↓
UnifiedRunWorkspace
```

G0→G6 labels may be displayed when supplied by scenario/runtime data. Rendering those labels does not activate GWC governance for DWO implementation.

## 6. UnifiedRunWorkspace component contract

```text
UnifiedRunWorkspace
├── WorkspaceHeader
├── ScenarioRunRail
├── RunHierarchy
├── RuntimeGraphCanvas
│   ├── GateCluster
│   ├── RuntimeNodeCard
│   ├── RuntimeEdge
│   └── MiniMap
├── NodeInspector
│   ├── Overview
│   ├── Files
│   ├── Artifacts
│   ├── Runbook
│   ├── History
│   ├── Checkpoints
│   └── Raw
├── NextFlowPanel
└── RuntimePlayer
```

Existing login-epic RuntimeGraphCanvas should be reused/refactored rather than rewritten.

Existing Node Architect inspector semantics should be promoted into the canonical NodeInspector.

## 7. Next Flow contract

Next Flow must be source-backed.

```ts
interface NextFlowProjection {
  currentNodeId: string | null;
  nextNodeId: string | null;
  reason: string | null;
  blocker: string | null;
  source: "DURABLE_RUNTIME" | "REPLAY_SNAPSHOT" | "FIXTURE";
  status: "RESOLVED" | "UNKNOWN" | "BLOCKED" | "CONFLICT";
}
```

Rules:

- no graph-position inference
- no "next node" from visual adjacency
- conflicting sources => CONFLICT
- missing source => UNKNOWN
- replay computes Next Flow only as-of selected historical sequence

## 8. Replay isolation

Replay keeps the same visual shell but a distinct data pipeline.

Inputs:
- exact run id
- durable canonical history
- selected durable sequence

Reducer rule:

```text
historicalEvents = canonicalEvents where sequence <= selectedSequence
snapshot = reduce(historicalEvents)
```

Forbidden:
- live subscriptions
- current authority merge
- events after selectedSequence
- fixture fallback in real mode

Failure states:
- missing canonical history -> PROJECTION_UNAVAILABLE
- invalid sequence -> REPLAY_POSITION_UNAVAILABLE
- digest/revision conflict -> fail closed

The old real replay placeholder:

```ts
dataSource === "mock" ? getMockProjectionEvents(runId) : []
```

must be removed.

## 9. Fixture Lab contract

DWO-UR-30-V1 must materialize 30 complete scenarios.

Each DEV-RUN-001..030 must provide:
- run/workspace model
- hierarchy
- dependency edges
- runtime nodes
- state/lifecycle
- authority/evidence where applicable
- timeline/replay history where applicable
- Next Flow
- node-owned detail panels

Catalog cards are navigation only.

DEV-RUN-020 must demonstrate same-revision relation conflict and fail closed.

No bespoke fixture workspace is allowed.

## 10. Dashboard aggregation contract

Dashboard uses normalized source-backed projections:

```ts
interface DashboardProjection {
  taskCount: number | null;
  runCounts: Record<string, number | null>;
  unresolvedCount: number | null;
  authorityWaitCount: number | null;
  degradedSourceCount: number | null;
  recentActivity: unknown[];
  needsAttention: unknown[];
}
```

If a source needed for an aggregate is unavailable, expose UNKNOWN/UNAVAILABLE rather than substituting fixture data.

## 11. Design tokens

Penpot DWO/Core is canonical visual input.

Initial tokens include:
- canvas/surface/subtle backgrounds
- default border
- primary/muted/faint text
- blue/green/amber/red/purple states
- spacing 4/8/12/16/20/24
- radius 6/8/10/12

Implementation should map these to CSS variables and Tailwind semantic aliases.

Do not scatter raw hex values across screen components.

## 12. Storybook contract

Use Storybook 8.6.x for the current React 18 / Next.js 14 codebase.

CSF3 stories should cover at least:

- RuntimeNodeCard: done / active / future / blocked / unknown
- NextFlowPanel: resolved / blocked / unknown / conflict / replay-as-of
- NodeInspector: every tab
- RuntimePlayer: live / replay / paused / start / end
- UnifiedRunWorkspace:
  - Login Auth simulated
  - Node Architect simulated
  - real live
  - replay
  - degraded
  - relation conflict
- Dashboard: healthy / attention / degraded

Use args for state variation and play functions for interaction where meaningful.

Storybook is an executable UI contract, not a production data source.

## 13. Playwright contract

Add Playwright E2E + visual regression.

Required navigation assertions:
- Dashboard -> Tasks
- Tasks -> Task Runs
- Task Runs -> Run Workspace
- Workspace LIVE -> Replay mode
- Replay -> LIVE
- Fixture catalog -> DEV-RUN-020 workspace

Required screenshot baselines:
- Dashboard
- Task Runs
- Unified Workspace LIVE
- Unified Workspace REPLAY
- Fixture Lab
- DEV-RUN-020 fail-closed

Use toHaveScreenshot with deterministic data and animations disabled.

Visual snapshots do not replace semantic assertions.

## 14. Verification layers

1. Vitest
   - pure adapters
   - reducers
   - replay isolation
   - Next Flow
   - fail-closed behavior
   - fixture invariants

2. Storybook
   - component/state contract
   - interaction play functions

3. Playwright
   - routing
   - mode switching
   - visual regression
   - critical semantic selectors

## 15. Definition of Done

Implementation is ready for independent certification only when:

- Penpot screen/component contract is represented in code
- Task and Task->Run paths are source-backed
- real replay is wired
- Replay is same workspace shell with isolated historical data
- 30/30 scenarios open as complete workspace simulations
- DEV-RUN-020 visibly fails closed
- Dashboard is operational, not decorative
- dev-only simulations are not primary product navigation
- no raw anchor navigation remains where Next Link/router semantics are expected
- Vitest green
- Storybook states green
- Playwright navigation + screenshots green
- PR remains Draft until independent review
