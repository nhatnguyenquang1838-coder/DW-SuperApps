# M5 · DW Run Observatory — Animated Hierarchical Run Graph · DESIGN CONTRACT

Status: DESIGN (pre-implementation). Branch `auto/SCRUM-555-dw-observation-m5-local-review-data-readiness`.
Re: GitHub #80 Controller seq=3 (`CORRECTION_REQUIRED_ANIMATED_HIERARCHICAL_RUN_UI`) + user redirect (design-first → architecture → implement; React Flow via Context7).

This artifact is the authoritative UI contract. Implementation MUST follow it; no free-form UI changes.

## 1. Goal

Render `/runs/[runId]` as an **animated hierarchical graph**: every step is one card (node), connected by **visible directional edges**. Active (current) card highlights/pulses; completed cards are stable. `/runs` stays clean/scannable.

## 2. Library decision (Context7-grounded)

- **React Flow `@xyflow/react`** (v12, repo already has `DagView.tsx` using it). Context7 lib `/xyflow/xyflow` (463 snippets, High reputation).
- Confirmed primitives: `nodeTypes`, `edgeTypes`, `MarkerType.ArrowClosed`, `BaseEdge`, `getBezierPath`, `fitView`, read-only props (`nodesDraggable=false`, `nodesConnectable=false`, `elementsSelectable=false`), animated edges.
- **No new dependency.** d3-hierarchy NOT needed — layout is deterministic from the explicit mock descriptor in `observatory.ts` (already source-backed).
- Animated entrance + pulse = CSS keyframes (added to globals.css), matching existing pattern.

## 3. Graph nodes (10, fixed contract)

| id | kind | label | status source |
|----|------|-------|---------------|
| `#70` | root | Parent SCRUM-555 | `nodes["70"].status` |
| `G2` | gate | G2 | `gates["G2-DW-OBS-M3M4-20260823-R1"].status` |
| `#71` | node | M0 | `nodes["71"].status` |
| `#72` | node | M1 | `nodes["72"].status` |
| `#73` | node | M2 | `nodes["73"].status` |
| `#74` | node | M3 | `nodes["74"].status` |
| `G3` | gate | G3 | `gates["G3"].status` |
| `G4` | gate | G4 | `gates["G4-DW-OBS-M3M4-20260823-R1"].status` |
| `#75` | node | M4 | `nodes["75"].status` |
| `#80` | issue | M5 review issue | fixed: `correction_required (active)` |

## 4. Hierarchy order & edges (parent/child, recorded — NOT inferred)

Vertical layout (x by depth column, y by order). Edges (source → target, label):

```
#70 ──parent->M0──▶ #71 ──M0->M1──▶ #72 ──M1->M2──▶ #73 ──M2->M3──▶ #74
#75 ──M3->M4──▶ #75 ──M4->review──▶ #80
G2 ──G2 approves M0──▶ #71
G3 ──G3 reviews M3──▶ #74
G4 ──G4 consumes M3──▶ #74
```

9 explicit edges. Gates attach as side branches to their target node. No edge is invented for real fixtures (connectors `[]` → React Flow renders no edges).

## 5. Card content fields (per node/edge)

Node card:
- badge: kind (ROOT/GATE/NODE/ISSUE)
- id (#70, G2, …)
- label (M0, G3, …)
- status (recorded)
- detail (gate meaning: lane approval / independent review / consumed-merged)
- incoming connector labels (recorded: "G2 → G2 approves M0")

Edge:
- directional marker `MarkerType.ArrowClosed`
- optional label (from connector.label)
- animated when target is active

## 6. Animation states

| state | trigger | visual |
|-------|---------|--------|
| pending | not yet revealed | opacity 0, translateY |
| active | id === activeId (`#80` in mock) | gentle pulse (box-shadow), accent border |
| complete | revealed & not active | stable, full opacity |
| blocked | status contains "blocked" | red border (reserved; not used by mock) |
| warning | status contains "warn"/anomaly | amber border (reserved; DUPLICATE anomaly surfaces here) |

Cards reveal sequentially (staggered `animation-delay` by index). Completed cards do NOT pulse.

## 7. Viewport behavior & mobile fallback

- Desktop/tablet: React Flow canvas, `fitView`, `proOptions.hideAttribution`, no pan-on-scroll zoom limit issues (fixed height 360px container).
- Mobile (<640px): React Flow still renders (it is responsive); `fitView` keeps all nodes visible; `Controls showInteractive={false}`. Touch pan enabled, zoom disabled on double-click (`zoomOnDoubleClick={false}`).
- Read-only always: `nodesDraggable={false}` `nodesConnectable={false}` `elementsSelectable={false}` `zoomOnDoubleClick={false}`.

## 8. Selectors / test IDs (every node/edge)

- Node wrapper: `data-testid="runflow-node"` + `data-node-id="#70"` (and each id)
- Node kind badge: `data-testid="node-badge"`
- Edge: `data-testid="runflow-edge"` + `data-edge-id="e-70-71"`
- Active card: `data-testid="runflow-node"` `data-active="true"`
- Root: `data-node-kind="root"`; gate: `data-node-kind="gate"`; issue: `data-node-kind="issue"`
- Container: `data-testid="run-graph-view"`

## 9. Data contract

- Source: `buildHierarchy(run, dataSource)` in `lib/observatory.ts` (already implemented seq=3). Returns `RunHierarchy { rootId, chain, gateIds, nodes[], connectors[] }`.
- Mock run `DW-OBS-M5-20260823-MOCK` → full hierarchy above. Real fixtures → best-effort from recorded gates/nodes, connectors `[]`.
- Supabase readiness shown in RootCard (already implemented): `SUPABASE_READINESS` constant.

## 10. Acceptance / verification (deterministic, not LLM judgment)

- Component test asserts every node id present via `data-node-id` selector (10 nodes).
- Test asserts each edge selector `data-edge-id` exists (9 edges).
- Test asserts `PROJECTION_UNAVAILABLE` NOT in mock-mode DOM.
- Test asserts React Flow read-only: container/instance props `nodesDraggable=false`, `nodesConnectable=false`, `elementsSelectable=false`.
- Test asserts `data-active="true"` on `#80`.
- DOM/text capture of `/runs` and `/runs/[runId]` (localhost proof).

## 11. Boundaries

- No Supabase migration/apply · no deploy/G6 · no main promotion · lockfile untouched.
- Open Draft PR to `pre-prod` only after design + architecture + implementation evidence ready.
