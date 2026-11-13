# Application-wide datasource selection

The shared layout owns the Real/Fixture selector. `changeDataSource` validates
and persists `dwo-data-source` as an HttpOnly, SameSite=Lax cookie at `/`.
`getRequestDataSource` reads it for each server request; no process-global state
or client-only dashboard state is used by application routes.

- Dashboard, Tasks, task runs, Run Explorer, run detail, replay and fixture
  evidence share the selection. Fixture task records load from the canonical
  file, not the former duplicated inline records.
- Run Explorer preserves the canonical 30 runs / 5 tasks and adds the separate
  DWO-WORK-DEMO-V1 pack: 9 runs / 3 tasks / 106 events / 23 evidence files.
  The combined preview is 39 runs / 8 tasks. Fixture Dashboard now classifies
  materialized work state; resolved membership no longer means completed work.
  See `dwo-v2/fixtures/DWO-WORK-DEMO-V1/README.md` for the story walkthrough.
- Explicit Real overrides a fixture environment default. Invalid cookie values
  resolve to Real. Separate browsers retain separate preferences.
- Production always resolves Real; server action rejects Fixture; all `/dev`
  paths are blocked in production. Non-production `/dev` paths also require
  the fixture selection, preventing fixture pages under the Real indicator.
- Selecting Real does not connect or configure any remote service. Missing real
  data remains unavailable. Legacy fixture activity is no longer shown as Real.
- Switching awaits the cookie action, then refreshes RSC/router data. The
  selector stays disabled during the action and the refresh transition.
  `router.refresh()` is not a full browser reload; prior claims to the contrary
  were incorrect.

## Verification

- `node node_modules/vitest/vitest.mjs run tests/unit/dwo/`: 82 files,
  848 tests passed after fuller fixture and inspector-hydration changes.
- `node scripts/typecheck-tests.mjs --strict`: 0 errors, baseline 0.
- `node node_modules/typescript/bin/tsc --noEmit`: exit 0.
- With local development server on `127.0.0.1:3001`, run:
  `node node_modules/@playwright/test/cli.js test --config playwright.datasource.config.ts`
  Result: 5 end-to-end tests passed using installed Chrome. Covers native select,
  cached Real route -> Fixture, 39 runs, 8 tasks, task detail, run detail, replay,
  reload persistence, evidence 200 in Fixture/404 in Real, direct `/dev` denial
  in Real, browser-context isolation, and switching back to Real.
  All nine demo run routes, artifact viewer, meaningful replay rewind/resume,
  and the 390px showcase layout were also exercised.
- Independent read-only review identified direct-dev-route mismatch and React18
  async pending-state gaps; both have explicit failing-then-passing regressions.

No database, credentials, webhook, GWC runtime, merge or deployment changes.
This is local/browser and test evidence, not a claim of exact-head hosted CI.
