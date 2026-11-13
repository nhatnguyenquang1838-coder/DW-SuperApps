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

There are **9 runs, 3 explicit task relations, 106 events and 23 evidence files**.
Each root has API/UI children and dependency edges. The combined preview shows
**39 runs and 8 tasks**. Source namespaces, sequence, synthetic timestamps,
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

Observed local validation: **848 unit tests / 82 files passed**, both typechecks
passed, **5 Chrome E2E tests passed**. Browser tests inspect all 9 new run routes,
artifact content, history rewind/resume, source isolation and 390px showcase
layout. Inspector tabs remain disabled until hydration to prevent lost first
clicks on freshly loaded pages. These are local results, not hosted CI claims.
