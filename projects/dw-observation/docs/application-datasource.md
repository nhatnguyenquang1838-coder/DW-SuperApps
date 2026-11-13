# Application-wide datasource selection

The shared layout owns the Real/Fixture selector. `changeDataSource` validates
and persists `dwo-data-source` as an HttpOnly, SameSite=Lax cookie at `/`.
`getRequestDataSource` reads it for each server request; no process-global state
or client-only dashboard state is used by application routes.

- Dashboard, Tasks, task runs, Run Explorer, run detail, replay and fixture
  evidence share the selection. Fixture task records load from the canonical
  file, not the former duplicated inline records.
- Run Explorer lists the canonical 30-run catalog in Fixture mode. The task
  relation file contains 5 tasks; these are not 30 tasks. Existing dashboard
  aggregate classification is unchanged by this source-routing fix.
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

- `node node_modules/vitest/vitest.mjs run tests/unit/dwo/`: 80 files,
  839 tests passed after the independent review corrections.
- `node scripts/typecheck-tests.mjs --strict`: 0 errors, baseline 0.
- `node node_modules/typescript/bin/tsc --noEmit`: exit 0.
- With local development server on `127.0.0.1:3001`, run:
  `node node_modules/@playwright/test/cli.js test --config playwright.datasource.config.ts`
  Result: 1 end-to-end test passed using installed Chrome. Covers native select,
  cached Real route -> Fixture, 30 runs, 5 tasks, task detail, run detail, replay,
  reload persistence, evidence 200 in Fixture/404 in Real, direct `/dev` denial
  in Real, browser-context isolation, and switching back to Real.
- Independent read-only review identified direct-dev-route mismatch and React18
  async pending-state gaps; both have explicit failing-then-passing regressions.

No database, credentials, webhook, GWC runtime, merge or deployment changes.
This is local/browser and test evidence, not a claim of exact-head hosted CI.
