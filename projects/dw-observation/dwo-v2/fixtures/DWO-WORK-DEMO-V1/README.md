# DWO-WORK-DEMO-V1 — synthetic work stories

This additive preview pack addresses the one-event-per-run limitation of the
sealed DWO-UR-30-V1 state catalog. It does not change that canonical 30-run pack,
its hashes, negative fixture or qualification receipts.

## Inspect in the app

Select **Fixture**, then open `/dashboard` or `/runs` and use **Explore work in
progress**. Normal task, workspace, artifact viewer and replay routes are reused.

| Task | Root run | Story |
| --- | --- | --- |
| DEMO-TASK-DELIVERY | DEMO-DELIVERY-ROOT | API + dashboard work accepted through G0–G6 |
| DEMO-TASK-BLOCKED | DEMO-BLOCKED-ROOT | API done; UI and parent wait, then are blocked with denied demo authority |
| DEMO-TASK-RETRY | DEMO-RETRY-ROOT | Verification fails, execution repairs, verification remains active |
| DEMO-TASK-RECURSIVE | DEMO-RECURSIVE-ROOT | ROOT → CHILD → two ATOMIC runs, each with G0–G6; graph replay starts at G0 |

There are **13 runs, 4 explicit task relations, 166 events and 35 evidence files**.
The three original stories have atomic API/UI children; the recursive story adds
an explicit CHILD level. The combined preview shows **43 runs and 9 tasks**.
Source namespaces, sequence, synthetic timestamps,
actors, event identity and human-readable summaries are materialized in the data.
Events use distinct per-run synthetic source streams, so a scenario union does
not create artificial gaps or duplicate identities.

- **Inspect work:** choose a hierarchy node; Artifacts opens execution,
  verification and, where present, handoff JSON in the existing artifact viewer.
- **Replay history:** Start → Step forward → Tip. Summaries describe the actual
  fictional work transition; cursor/digest and all replay panes remain aligned.
- **Dashboard:** buckets use materialized runtime state, not successful relation
  resolution. Child acceptance never implicitly completes its open parent.
- Evidence belongs to the exact run and allowlisted pack. Real/production cannot
  serve these files through fixture endpoints.

## Truth and limitations

### Recursive G0–G6 walkthrough

Open `/runs/DEMO-RECURSIVE-ROOT` with Fixture selected. This is not another
workspace implementation: one prefix cursor drives the existing
`UnifiedRunWorkspace` graph, the seven-gate history matrix and source event log.

```text
DEMO-RECURSIVE-ROOT   ROOT
└─ DEMO-RECURSIVE-CHILD   CHILD
   ├─ DEMO-RECURSIVE-API   ATOMIC
   └─ DEMO-RECURSIVE-UI    ATOMIC (depends on API)
```

All four runs have explicit G0–G6 declarations and history. The scenario has
60 interleaved events; root/child each have 16, atomics each have 14.

| Control / prefix cursor | Observable source-backed state |
| --- | --- |
| Start at G0 / 1 | Root G0 ACTIVE; future node states NOT OBSERVED |
| Atomics complete / 40 | Both atomics ACCEPTED; child and root G2 WAITING / OPEN |
| Child complete / 50 | Child ACCEPTED; root still G2 WAITING / OPEN |
| Root G6 accepted / 60 | Root independently ACCEPTED; all four G0–G6 histories passed |

The existing workspace step, scrubber and playback controls update the same
cursor. Query link `/runs/DEMO-RECURSIVE-ROOT?mode=replay&seq=40` selects the
fixture subtree prefix cursor (not a per-run source sequence). Rewinding clears
future evidence from the workspace. Full-tip artifact inspection becomes
available only at the complete scenario tip. These are immutable fixture replay
events, not actual live production streaming or a publisher certification.

### Synthetic evidence boundary

All stories, code/artifact text, test outcomes, actors and timestamps are
**fictional synthetic fixture content**, not records of an actual delivery.
No approval, merge, deployment, qualification or remote database effect occurs.
Qualification remains UNKNOWN/PENDING without a genuine compatible receipt.
Runbook, TaskController/Executor-history and checkpoint tabs remain unavailable
where there is no matching source contract; raw work logs are not relabelled as
those typed records. Full-tip evidence is not exposed as proof for early replay
cuts. Successful app tests verify the observer, not the fictional story outcomes.

## Reproduce

From the DWO package directory:

```sh
python scripts/materialize-work-demo.py
node node_modules/vitest/vitest.mjs run tests/unit/dwo/
node scripts/typecheck-tests.mjs --strict
node node_modules/typescript/bin/tsc --noEmit
# With local dev server already running on 127.0.0.1:3001:
node node_modules/@playwright/test/cli.js test --config playwright.datasource.config.ts
```

Observed local validation: **853 unit tests / 84 files passed**, both typechecks
passed, **6 Chrome E2E tests passed**. Browser tests inspect all 9 original demo run routes,
artifact content, history rewind/resume, source isolation and 390px showcase
layout, plus recursive graph/matrix state changes and independent parent
transitions at prefixes 1, 40, 50 and 60. Inspector tabs remain disabled until hydration to prevent lost first
clicks on freshly loaded pages. These are local results, not hosted CI claims.
