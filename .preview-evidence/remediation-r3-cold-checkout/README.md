# R3 clean-checkout type regression

This addendum supersedes the latest-source manifest in the preceding R3 CI recovery pack. Its ten cumulative source/config/test blobs include middleware.ts. Earlier packs remain historical source-bound evidence, not relabeled final-head runs.

Hosted CI at00759cb0 successfully loaded the corrected workflow and ran the full Vitest suite, but strict baseline0 then rejected TS2559. Exact run: https://github.com/nhatnguyenquang1838-coder/DW-SuperApps/actions/runs/41144349478. The summary wrapper hid the raw file diagnostic; its failure was real and preserved, not waived.

Lead reproduced the real compiler error in scratch without generated next-env/.next type files: middleware.ts(20,45), ProcessEnv has no properties in common with DevRouteEnvironment. A previously generated local Next ambient declaration had masked the weak-type mismatch.

- New regression uses the real repository TypeScript compiler against actual middleware.ts, extends the app strict compiler options, includes only middleware and Node types, and excludes generated next-env/.next types. It creates/removes only its own unique scratch config. RED: one failing test, real TS2559 and normal Vitest exit1.
- Minimal fix passes NODE_ENV and OBSERVATORY_DATA_SOURCE explicitly into the existing middleware factory. Factory production404 predicate and matcher are unchanged. No cast/suppression, type-debt allowance, fallback, dependency or source-mode change.
- GREEN: all11 CI delivery-contract tests, including real cold compiler regression; strict test typecheck errors0/baseline0; app typecheck pass. No new full-suite count is claimed here. Final full hosted Vitest/Python/Chromium/build results and fresh exact-head independent reviews must be read back separately and published in the PR body.

Reducer/current-subject reader, identity metadata, fixtures/receipts/contracts, routes, Python and .gwc remain unchanged by this correction. Qualification stays UNKNOWN / SEMANTIC_SOURCE_VERIFIER_UNAVAILABLE without an independent authentic canonical source-artifact verifier. No merge, deploy, production-data access, lifecycle/authority mutation, baseline increase or skip was introduced. Local production build/ingress will be re-exercised at the final committed head; results belong to the PR target rather than an invented pre-execution claim in this commit.
