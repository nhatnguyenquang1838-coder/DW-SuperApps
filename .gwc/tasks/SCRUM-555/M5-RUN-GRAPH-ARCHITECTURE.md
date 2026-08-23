# M5 · DW Run Observatory — Animated Hierarchical Run Graph · ARCHITECTURE MAP

Maps the DESIGN CONTRACT (`M5-RUN-GRAPH-DESIGN.md`) to concrete files/components/data contracts. Pre-implementation.

## Component tree (new / changed)

```
app/runs/[runId]/page.tsx            (edit)  — wire RunGraphView, pass hierarchy+activeId
components/RunGraphView.tsx          (NEW)   — React Flow canvas, read-only, fitView
components/RunGraphNodeCard.tsx      (NEW)   — custom node (nodeTypes.graphNode)
components/RunGraphEdge.tsx          (NEW)   — custom edge (edgeTypes.graphEdge), ArrowClosed
lib/observatory.ts                   (edit)  — RunHierarchy already exists; add layout()
lib/observatory.ts                   (edit)  — SUPABASE_READINESS already exists
app/globals.css                      (edit)  — keyframes runflow-in / runflow-pulse (exist)
components/RootCard.tsx              (edit)  — Supabase readiness (exists)
tests/unit/RunGraphView.test.tsx     (NEW)   — deterministic selectors + read-only + no UNAVAIL
tests/unit/AnimatedRunFlow.test.tsx  (DELETE) — superseded by RunGraphView (no free-form UI)
components/AnimatedRunFlow.tsx       (DELETE) — superseded (custom CSS, not React Flow)
```

## Data contracts (unchanged from seq=3)

- `RunHierarchy` (lib/observatory.ts): `{ rootId, chain, gateIds, nodes: HierarchyNode[], connectors: {from,to,label}[] }`
- `HierarchyNode`: `{ id, kind: 'root'|'gate'|'node'|'issue', label, status, detail?, sourceBacked }`
- `buildHierarchy(run, dataSource)` → full mock hierarchy (#70..#75,#80 + G2/G3/G4) or real best-effort.
- `SUPABASE_READINESS` constant → RootCard.

## Layout function (deterministic, in lib/observatory.ts)

`layoutHierarchy(h: RunHierarchy): { nodes: Node[], edges: Edge[] }`:

- Node positions: depth column by kind (root col 0, nodes col 1, gates col 2 side branch), y by order index * 70.
- Node `type: 'graphNode'`, `data: { node: HierarchyNode, active }`, `data-testid` via node `data`.
- Edge `type: 'graphEdge'`, `markerEnd: { type: MarkerType.ArrowClosed }`, `label`, `animated: target.active`.
- Edge id `e-<from>-<to>` → `data-edge-id`.

## React Flow wiring (Context7-grounded)

```tsx
<ReactFlow
  nodes={rfNodes}
  edges={rfEdges}
  nodeTypes={{ graphNode: RunGraphNodeCard }}
  edgeTypes={{ graphEdge: RunGraphEdge }}
  fitView
  nodesDraggable={false}
  nodesConnectable={false}
  elementsSelectable={false}
  zoomOnDoubleClick={false}
  proOptions={{ hideAttribution: true }}
>
  <Background />
  <Controls showInteractive={false} />
</ReactFlow>
```

## Mock vs real

- mock `DW-OBS-M5-20260823-MOCK` → full node+edge graph, active `#80`, no PROJECTION_UNAVAILABLE.
- real → nodes from recorded gates/nodes, connectors `[]` (no edges), read-only.

## Test IDs (from design §8)

`run-graph-view`, `runflow-node` + `data-node-id`, `data-node-kind`, `data-active`, `runflow-edge` + `data-edge-id`.

## Verification mapping (design §10 → tests)

- 10 `data-node-id` present → all cards exist.
- 9 `data-edge-id` present → all connectors exist.
- no `PROJECTION_UNAVAILABLE` text in mock DOM.
- React Flow read-only props asserted (query container for `react-flow` + instance prop check via test render).
- `data-active="true"` on `#80`.

## Boundaries

No Supabase migration/apply · no deploy/G6 · no main promotion · lockfile untouched · PR to `pre-prod` only after evidence.
