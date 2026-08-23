# Login Epic GWC Runtime Graph — Acceptance (SCRUM-555 / M5)

> Blocker checklist for Controller seq=7 G3 HOLD. All items below are implemented and verified by
> `tsc --noEmit` (clean) + `vitest run` (205 passing) + deterministic DOM/screenshot proof.

## Dataset (hard requirement)
- [x] `epic.epic_id === "LOGIN-CAPABILITY"`
- [x] `epic.run_count === 10` (LOGIN-R00-EPIC-BOOT … LOGIN-R09-OBSERVATORY-DEPLOY-BOUNDARY)
- [x] `epic.runtime_node_count === 243`
- [x] every run includes all 7 gates G0_CONTEXT…G6_PRODUCTION
- [x] every route node id exists in its run's gates

## UI — run graph
- [x] Top: 10 large run cards via `EpicRunRail` (`data-testid="login-epic-run-card"`, `data-run-id`).
- [x] Run arrows R00→R09 (`data-testid="login-epic-run-arrow"`, 9 edges).
- [x] Clicking a run loads that run's runtime graph (`selectRun` resets cursor + selection).

## UI — run-level graph
- [x] Large React Flow canvas (not static rows): `RuntimeGraphCanvas` (`data-testid="runtime-graph-canvas"`).
- [x] Gate clusters G0_CONTEXT→…→G6_PRODUCTION (`data-testid="runtime-gate-cluster"`, `data-gate-id`).
- [x] Gate dependency arrows visible (`data-testid="runtime-gate-arrow"`, 6 edges).
- [x] Runtime Node cards inside each Gate cluster (`data-testid="runtime-node-card"`, `data-node-id`, `data-active`).
- [x] Node route arrows follow `run.route` (`data-testid="runtime-route-arrow"`); active edge animates
      (`data-testid="runtime-active-edge"`).

## UI — player
- [x] first / prev / play-pause / next / last / scrubber / speed / REPLAY / LIVE SIM (`RuntimePlayer`).
- [x] LIVE SIM starts at node 1 and advances the event stream (`mode==="LIVE_SIM"` auto-plays from cursor 0).
- [x] Follow cursor auto-centers viewport to active node (`setCenter`); manual pan disables Follow
      (blocker #3: `onMoveStart` + `programmaticMove` ref; `data-testid="runtime-follow-cursor" data-follow`).

## UI — zoom
- [x] Zoom in / zoom out / fit / reset (`runtime-zoom-in` / `runtime-zoom-out` / `runtime-fit` / `runtime-reset`).

## UI — right panel tabs
- [x] Overview / Files / Artifacts / Runbook / History / Raw (`runtime-detail-tab-<id>`).
- [x] History tab splits `TaskController History` and `Executor History`.
- [x] File / artifact / checkpoint buttons open modal preview (`runtime-file-read` / `runtime-file-write` /
      `runtime-artifact` / `runtime-checkpoint`; `ArtifactModal` `data-testid="artifact-modal"`).

## Blockers addressed (seq=7)
1. [x] Delivery docs added: `login-epic-runtime-graph-design.md`, `login-epic-runtime-graph-acceptance.md`.
2. [x] Active edge animation deterministic: `RuntimeEdge` forwards `className="runtime-active-edge"` +
      explicit animated stroke; CSS keyframes; **test: active edge has `runtime-active-edge` class + style**.
3. [x] Manual pan/zoom disables Follow; programmatic `setCenter` does NOT (ref flag); **test: simulated
      viewport interaction flips `data-follow` OFF; follow-cursor centering keeps it ON**.
4. [x] REPLAY click-to-rewind: `onSelectNode` sets `cursor=getRouteIndex(run,nodeId)` in REPLAY; LIVE_SIM
      inspects only; **test: clicking node in REPLAY rewinds cursor to its route index**.
5. [x] Enriched source-code write previews for `app/login/page.tsx`, `components/auth/LoginShell.tsx`,
      `components/auth/LoginForm.tsx`, `lib/contracts/login.ts`, `app/api/login/route.ts`,
      `lib/api/loginClient.ts` (deterministic, node-agnostic).
6. [x] Strengthened tests: active edge marker, REPLAY rewind, LIVE_SIM fake-timer advance, manual
      viewport disables Follow, required docs exist.
7. [x] Screenshot evidence after patch: epic overview (10 cards), selected run G0→G6 clusters + arrows,
      LIVE_SIM active node + animated edge, right-panel file/artifact modal.

## Validation evidence
- `tsc --noEmit` → exit 0.
- `vitest run` → 14 files / 205 tests passing (incl. 19 Login Epic tests, 5 new blocker tests).
- localhost `http://127.0.0.1:3000/runs/login-epic` → HTTP 200; 10 run cards; 243 NODES badge;
  all required `data-testid` selectors present.
- 4 screenshots delivered in the executor mailbox reply thread.

## Exclusions
No Supabase migration/apply · no deploy/G6 · no pre-prod→main · no GWC repo mutation · no new deps.
PR #81 remains DRAFT, not merged, awaiting G3 independent review.
