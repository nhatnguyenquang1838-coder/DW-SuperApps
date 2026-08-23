# Login Epic Runtime Graph — Clean UI Source Architecture

Scope: SCRUM-555 / DW Run Observatory / PR #81

This document is the implementation architecture for the user-approved `Login Capability Epic -> 10 Runs -> G0-G6 -> Runtime Nodes` view. It is meant to prevent Hermes from copying a one-off HTML prototype into production source. The HTML is a reference artifact only; the repo implementation should be typed, composable, and testable.

## 1. Mental model

```text
Epic
  Run[]
    Gate[]
      RuntimeNode[]
        fileReads[]
        fileWrites[]
        artifacts[]
        runbook[]
        taskControllerHistory[]
        executorHistory[]
        checkpoints[]
```

Do not render `Gate -> Task Cards`. Render `Gate -> Runtime Nodes`. A Run is not a UI section; it is a runtime object with its own G0->G6 graph.

## 2. Source file layout

```text
projects/dw-observation/
  fixtures/
    login_epic_10_runs_gwc_taskcontroller_data.json

  lib/
    loginEpicRuntimeGraph.ts
    loginEpicRuntimeSelectors.ts
    loginEpicRuntimeValidation.ts

  components/
    login-epic/
      LoginEpicRunGraph.tsx
      EpicRunRail.tsx
      RuntimeGraphCanvas.tsx
      GateClusterNode.tsx
      RuntimeNodeCard.tsx
      RuntimeEdge.tsx
      RuntimePlayer.tsx
      RuntimeDetailsPanel.tsx
      ArtifactModal.tsx
      MiniMap.tsx

  app/
    runs/
      login-epic/
        page.tsx

  tests/
    unit/
      loginEpicRuntimeGraph.test.ts
      LoginEpicRunGraph.test.tsx
```

If the current repo structure prefers `components/` flat files, that is acceptable, but component boundaries must remain clear.

## 3. Data contracts

### `LoginEpicRuntimeFixture`

```ts
export type LoginEpicRuntimeFixture = {
  epic_id: 'LOGIN-CAPABILITY';
  title: string;
  run_count: 10;
  runtime_model: string;
  runs: LoginEpicRun[];
};
```

### `LoginEpicRun`

```ts
export type LoginEpicRun = {
  id: string;
  index: number;
  slug: string;
  title: string;
  objective: string;
  run_kind: 'planning' | 'design' | 'implementation' | 'quality' | 'observability_deploy_boundary';
  allowed_paths: string[];
  forbidden_actions: string[];
  gates: LoginEpicGate[];
  route: Array<{ gate_id: LoginEpicGateId; node_id: string }>;
  status: string;
  summary: string;
};
```

### `LoginEpicGate`

```ts
export type LoginEpicGateId =
  | 'G0_CONTEXT'
  | 'G1_ALIGNMENT'
  | 'G2_EXECUTION'
  | 'G3_PR'
  | 'G4_MERGE'
  | 'G5_DEPLOY'
  | 'G6_PRODUCTION';

export type LoginEpicGate = {
  id: LoginEpicGateId;
  label: string;
  summary: string;
  x: number;
  y: number;
  w: number;
  h: number;
  nodes: LoginEpicRuntimeNode[];
  gateArtifacts: string[];
  taskControllerHistory: string[];
  executorHistory: string[];
};
```

### `LoginEpicRuntimeNode`

```ts
export type LoginEpicRuntimeNode = {
  gate_id: LoginEpicGateId;
  id: string;
  title: string;
  family: string;
  type: string;
  boundary: string;
  purpose: string;
  fileReads: string[];
  fileWrites: string[];
  artifacts: string[];
  runbook: string[];
  taskControllerHistory: string[];
  executorHistory: string[];
  checkpoints: string[];
  x: number;
  y: number;
  w: number;
  h: number;
};
```

## 4. Pure runtime engine

`lib/loginEpicRuntimeGraph.ts` should contain pure functions only. No React, no DOM, no browser APIs.

Required functions:

```ts
export function validateLoginEpicFixture(fixture: LoginEpicRuntimeFixture): ValidationResult;
export function getRun(fixture: LoginEpicRuntimeFixture, runId: string): LoginEpicRun;
export function getGate(run: LoginEpicRun, gateId: LoginEpicGateId): LoginEpicGate;
export function getRuntimeNode(run: LoginEpicRun, nodeId: string): { gate: LoginEpicGate; node: LoginEpicRuntimeNode };
export function getRouteIndex(run: LoginEpicRun, nodeId: string): number;
export function clampCursor(run: LoginEpicRun, cursor: number): number;
export function getActiveRoute(run: LoginEpicRun, cursor: number): { gate_id: LoginEpicGateId; node_id: string };
export function getNodeState(run: LoginEpicRun, nodeId: string, cursor: number): 'done' | 'active' | 'future';
export function getGateState(run: LoginEpicRun, gateId: LoginEpicGateId, cursor: number): 'done' | 'active' | 'future' | 'empty';
export function buildGateEdges(run: LoginEpicRun): RuntimeEdgeModel[];
export function buildRouteEdges(run: LoginEpicRun): RuntimeEdgeModel[];
export function makeArtifactPreview(args: { run: LoginEpicRun; gate?: LoginEpicGate; node?: LoginEpicRuntimeNode; path: string; cursor: number }): string;
```

## 5. Rendering architecture

### `LoginEpicRunGraph.tsx`

Top-level client state owner.

Owns:

```ts
selectedRunId
cursor
mode: 'REPLAY' | 'LIVE_SIM'
playing
speedMs
selectedKind: 'run' | 'gate' | 'node'
selectedId
detailTab
artifactModalState
viewportState
followCursor
```

Delegates:

- `EpicRunRail` renders the 10-run epic graph.
- `RuntimeGraphCanvas` renders selected run's G0->G6 graph.
- `RuntimePlayer` renders transport controls.
- `RuntimeDetailsPanel` renders selected object details.
- `ArtifactModal` renders preview content.

### `EpicRunRail.tsx`

Inputs:

```ts
runs: LoginEpicRun[];
selectedRunId: string;
onSelectRun(runId: string): void;
```

Requirements:

- exactly 10 run cards.
- run arrows R00 -> R09.
- clicking a run resets cursor to 0 and loads the run-level graph.

### `RuntimeGraphCanvas.tsx`

Use React Flow if staying consistent with M5. If not using React Flow, a custom SVG/HTML canvas is acceptable only if selectors and test coverage are deterministic.

Required visible parts:

- Gate clusters as large containers.
- Gate dependency arrows G0 -> G6.
- Runtime node cards inside each Gate.
- Route arrows from `run.route`.
- Active node card highlighted.
- Active route edge animated.
- Follow cursor centers viewport on active node.
- Manual pan disables follow.
- Zoom in/out/fit/reset.

React Flow recommended mapping:

```ts
nodeTypes = {
  gateCluster: GateClusterNode,
  runtimeNode: RuntimeNodeCard,
};
edgeTypes = {
  runtimeEdge: RuntimeEdge,
};
```

Gate clusters can be implemented either as:

1. group nodes with parented runtime node children, or
2. absolutely positioned cluster backgrounds plus child runtime nodes.

Pick the implementation that keeps labels, click handling, and tests reliable.

### `RuntimeDetailsPanel.tsx`

Tabs:

- Overview
- Files
- Artifacts
- Runbook
- History
- Raw

History tab must split:

```text
TaskController History
Executor History
```

Files tab must split:

```text
File Reads
File Writes / Source-code writes
```

Artifacts tab must include:

```text
Artifacts
Checkpoints
```

All file/artifact/checkpoint rows must be clickable and open `ArtifactModal`.

### `ArtifactModal.tsx`

Inputs:

```ts
path: string;
content: string;
onClose(): void;
```

Preview generation belongs in pure lib (`makeArtifactPreview`), not in modal UI.

Source-code previews must support deterministic examples for:

```text
app/login/page.tsx
components/auth/LoginShell.tsx
components/auth/LoginForm.tsx
lib/contracts/login.ts
app/api/login/route.ts
lib/api/loginClient.ts
```

## 6. Selector contract

Required test selectors:

```text
data-testid="login-epic-run-graph"
data-testid="login-epic-run-card" data-run-id="LOGIN-R00-EPIC-BOOT"
data-testid="login-epic-run-arrow"
data-testid="runtime-graph-canvas"
data-testid="runtime-gate-cluster" data-gate-id="G0_CONTEXT"
data-testid="runtime-gate-arrow"
data-testid="runtime-node-card" data-node-id="..."
data-testid="runtime-route-arrow"
data-testid="runtime-active-edge"
data-testid="runtime-player"
data-testid="runtime-player-first"
data-testid="runtime-player-prev"
data-testid="runtime-player-play"
data-testid="runtime-player-next"
data-testid="runtime-player-last"
data-testid="runtime-player-scrubber"
data-testid="runtime-player-speed"
data-testid="runtime-live-sim"
data-testid="runtime-follow-cursor"
data-testid="runtime-zoom-in"
data-testid="runtime-zoom-out"
data-testid="runtime-fit"
data-testid="runtime-reset"
data-testid="runtime-details-panel"
data-testid="runtime-detail-tab-overview"
data-testid="runtime-detail-tab-files"
data-testid="runtime-detail-tab-artifacts"
data-testid="runtime-detail-tab-runbook"
data-testid="runtime-detail-tab-history"
data-testid="runtime-detail-tab-raw"
data-testid="runtime-file-read"
data-testid="runtime-file-write"
data-testid="runtime-artifact"
data-testid="runtime-checkpoint"
data-testid="artifact-modal"
```

## 7. Validation requirements

Unit tests:

- fixture has exactly 10 runs.
- total runtime node count is exactly 243.
- every run has all seven gates.
- every route node exists in its gate.
- every node has non-empty `fileReads`, `fileWrites` or `artifacts`, `runbook`, `taskControllerHistory`, and `checkpoints`.
- G6 in non-production runs records not-applicable boundary; R09 records production boundary nodes.

Component tests:

- epic graph renders 10 run cards.
- selecting each run updates selected run title and graph.
- run-level graph shows all 7 gates.
- route arrows and gate arrows are represented in DOM or source-backed model.
- player changes cursor.
- live sim advances from first node.
- follow cursor centers active node or triggers the documented viewport callback.
- zoom/fit/reset buttons update viewport state.
- right panel tabs switch content.
- artifact modal opens from file/artifact/checkpoint button.
- history tab includes both TaskController History and Executor History.

Browser proof / screenshot:

Hermes must provide at least four screenshots or screenshot artifacts in Slack:

1. Epic overview with 10 run cards.
2. Selected run showing G0->G6 gate clusters and arrows.
3. LIVE SIM/player active node and animated edge.
4. Details panel with file/artifact modal open.

If screenshot capture fails, Hermes must show the exact failing command and provide DOM proof, but must attempt screenshot first.

## 8. Boundaries

No Supabase migration/apply.
No deploy/G6 action.
No pre-prod->main.
No unrelated lanes.
No GWC repo mutation.
No force-push/history rewrite.
No source generation from LLM-only inference; source must derive from the tracked fixture and pure runtime selectors.
