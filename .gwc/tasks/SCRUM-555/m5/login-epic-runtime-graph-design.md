# Login Epic GWC Runtime Graph — Design (SCRUM-555 / M5)

> Executor delivery doc for Controller seq=6 → seq=7 (G3 HOLD / REQUEST CHANGES).
> Route: `app/runs/login-epic` (new). Mental model and data shape follow the
> Controller-transferred `LOGIN_EPIC_TRANSFER_README` + `login_epic_ui_source_architecture`.

## Mental model
```
Epic: LOGIN-CAPABILITY
  -> exactly 10 Runs (LOGIN-R00-EPIC-BOOT .. LOGIN-R09-OBSERVATORY-DEPLOY-BOUNDARY)
      -> each Run owns G0_CONTEXT .. G6_PRODUCTION
          -> each Gate owns Runtime Nodes
              -> each Node owns fileReads / fileWrites / artifacts /
                 runbook / TaskController history / Executor history / checkpoints
```
Node is the unit of runtime; artifact/runbook/history/checkpoints are children/details of a node.

## Fixture contract (generated, deterministic)
- `fixtures/login_epic_10_runs_gwc_taskcontroller_data.json` — canonical fixture, emitted as
  `window.EPIC = {...}` by the transferred `login_epic_reference_generator.py`.
- `run_count = 10`, `runtime_node_count = 243` (7 gates × (24 for 7 runs, 25 for 3 runs) = 243),
  every run includes all 7 gates G0_CONTEXT…G6_PRODUCTION.
- Repo-root siblings (reference/proof only, NOT copied into source): `*.raw.json`, `*.reference.html`.

## Architecture (modular, clean separation of pure engine vs UI)
- `lib/loginEpicRuntimeGraph.ts` — **pure engine only** (no React/DOM). Route-derived timeline is
  the single source of truth: `getRun/getGate/getRuntimeNode/getRouteIndex/clampCursor/getActiveRoute/
  getNodeState/getGateState/buildGateEdges/buildRouteEdges/makeArtifactPreview`.
- `lib/loginEpicRuntimeValidation.ts` — `validateLoginEpicFixture` (10 runs, 243 nodes, 7 gates,
  every route node exists, required non-empty fields).
- `lib/loginEpicFixture.ts` — deterministic loader (strips the `window.EPIC` wrapper; one source of truth).
- `components/login-epic/*` (10 components):
  - `LoginEpicRunGraph` — state owner (cursor/mode/speed/playing/selection/followCursor/modal).
  - `EpicRunRail` — top 10 run cards + R00→R09 arrows; clicking a run loads its graph.
  - `RuntimeGraphCanvas` — React Flow: gate clusters G0→G6 + node cards + gate/route arrows +
    follow-cursor (`setCenter`) + zoom in/out/fit/reset. `onMoveStart` disables Follow on user pan/zoom.
  - `GateClusterNode` — large G0…G6 container with header + state.
  - `RuntimeNodeCard` — node card (`data-node-id`, `data-active`); carries Handle in/out.
  - `RuntimeEdge` — forwards `className="runtime-active-edge"` + explicit animated yellow stroke on the
    active route edge (deterministic animation marker, independent of React Flow theme).
  - `RuntimePlayer` — first/prev/play-pause/next/last/scrubber/speed/REPLAY/LIVE_SIM.
  - `RuntimeDetailsPanel` — 6 tabs Overview/Files/Artifacts/Runbook/History/Raw. History splits
    TaskController & Executor; Files splits reads/writes; Artifacts incl. checkpoints.
  - `ArtifactModal` — centered modal, dark backdrop, synthetic preview (no real secrets).
  - `MiniMap` — compact 7-gate overview; click centers a gate.
- `app/runs/login-epic/page.tsx` — server loader (loads fixture via `lib/loginEpicFixture`).
- `app/globals.css` — `leg-*` styles + `@keyframes runtime-edge-dash` + `.runtime-active-edge` rule.

## Key interactions
- **REPLAY click-to-rewind** (blocker #4): in REPLAY mode, clicking a runtime node sets
  `cursor = getRouteIndex(run, nodeId)` and selects it. In LIVE_SIM, click only inspects (no rewind)
  so the running event stream continues.
- **Follow auto-center** (blocker #3): programmatic `setCenter` wraps in a `programmaticMove` ref flag
  so it does NOT disable Follow; only genuine user pan/zoom (`onMoveStart` with `programmaticMove=false`)
  turns Follow OFF. The Follow button also toggles manually (`data-follow="on|off"`).
- **Active edge animation** (blocker #2): the route edge at index === cursor gets `animated: true`,
  `className: "runtime-active-edge"`, and an explicit `strokeDasharray` + `animation: runtime-edge-dash`.
  `RuntimeEdge` forwards the class to the `.react-flow__edge` wrapper so tests assert
  `.react-flow__edge.runtime-active-edge` deterministically.

## Exclusions (preserved)
No Supabase migration/apply · no deploy/G6 · no pre-prod→main · no GWC repo mutation · no new deps.
