# PR130 R3 — source identity and CI delivery evidence

Recorded UTC: 2026-10-30T23:14:54.574144+00:00

**Code candidate:** `5d2bf7672ad80bd282bcee6b68d533fc3420ae8f`. Parent: `baffdb08d91a84435376248ee7e1a0ffcaf6eebf`. Branch `integration/SCRUM-820-dwo-v2`.

This R3 pack supersedes the R2 *current-version availability* limitation, not its historical facts. The final evidence-only delivery commit is identified in the PR body. Its nine source/config/test blobs must match `source-manifest.json`; changing only evidence does not silently claim that runtime source identity SHA stayed identical.

## Changes
- Published NEW source-owned `dwo.reducer/2` metadata consumed by both reducer and current-subject reader. This is not a claim that old synthetic receipts authenticated the new implementation. Existing fixture/receipt/contract/baseline artifact bytes remain unchanged.
- Current subject reads admitted tracked/clean source from immutable Git blobs at a captured SHA and resolved application prefix. Visible dirty/untracked/missing source fails closed; assume-unchanged worktree tampering cannot alter the committed-source digest. Malformed history, blank/duplicate source event identities/positions and ambiguous declarations return unavailable rather than being silently filtered.
- Corrected positive drift tests to require a nonnull changed digest. Route wiring covers UNKNOWN and DRIFTED independently of incidental dirty-worktree status; it observes the real fixture model dispatch and preserves authority/mutation false.
- Extended the existing read-only `typecheck-tests` CI job without changing its triggers or job identity. It now executes full Vitest, both test/app typechecks, Python3.12 installed qualification extras and real LangGraph imports, no-skips/nonempty JUnit guard, explicit fixture Chromium E2E with retries0 and a mock-source production build. Diagnostics upload always. Semantic screenshots are not OS pixel-baseline certification.
- Strict test typecheck allowance is now **0**, with the old86-error metadata retained explicitly as historical provenance. No baseline increase, ignored suite or diagnostic suppression.

## Actual verification
| Check | Result |
|---|---|
| Lead full Vitest | 77 files / 1,056 tests passed |
| Application typecheck | passed |
| Strict test typecheck | errors0 / baseline0 / delta+0 |
| Python with installed LangGraph/checkpoint-sqlite | 155 tests +4 subtests passed; no skips |
| Focused source/route/CI tests after code commit | 3 files /29 tests passed |
| Chromium cold-start on clean code candidate | 6 passed, retries0; seven screenshots |
| Production build after interrupted wrapper recovery | exit0; `r3-next-build-resumed.log` |
| Local production ingress with fixture override | 8 dev paths404; tasks200/unavailable/no fixture badge; owned server stopped |
| CI guard verification | contract9/9; YAML parse and11 Bash run blocks; exact XML guard accepted real no-skip JUnit and rejected explicit skip/empty fixtures |

The initial build wrapper was interrupted after compilation/artifact output; its exit was not accepted as success. With no remaining Next process, the build was rerun and exited0 before the actual HTTP probes. Old R2 logs were not relabeled as R3 results. Normalized logs remove ANSI/trailing whitespace only; raw logs remain in task scratch.

The sixth browser case proves historical receipt DRIFTED on canonical run, dev run, replay and Task-root routes using the actual default Git-backed reader. It also preserves negative020 and G5 WAITING through the existing cases. All UI/HTTP evidence here is localhost, not a deployment or production service test.

## Independent review and CI target readback

Fresh Pattern E code reviews must be run against the **final delivery HEAD**, using actual bmad/designer profiles and the session-selected gpt-6.1-sol/openai-codex route. The included route readback is a smoke only, not a review verdict. Actual structured reviewer receipts, source-claim reconciliation, runtime model/provider/fallback readback and final hosted CI results are attached or embedded in the PR body after this evidence commit, so those receipts do not change the reviewed HEAD merely by being committed to it.

## Remaining boundaries

- Full authentic GWC semantic source-artifact verification is still unavailable. Python qualification remains UNKNOWN with `SEMANTIC_SOURCE_VERIFIER_UNAVAILABLE`; this repair does not fabricate a producer, grant authority, mutate lifecycle or certify a release.
- `.gwc` provenance correction remains separately scoped and untouched. No review threads are automatically resolved. No merge/readiness/deploy/production-data operation is authorized.
- Synthetic historical receipts remain historical. DRIFTED means current subject differs; it is not a fresh qualification.
- Existing Next `devIndicator`, login-epic hook dependency, Node test and Python dependency deprecation warnings remain visible; no skip/baseline relaxation masks them.
- Windows local verification is recorded here; hosted Linux execution is a separate CI result. Named screenshot capture is not Darwin/Linux visual baseline certification.

## Reproduce

From `projects/dw-observation`, use pinned dependencies and an installed qualification/test Python environment:

```bash
pnpm run test --pool=threads --maxWorkers=1 --minWorkers=1
pnpm run typecheck
pnpm run typecheck:tests:strict
python -m pytest -q
PLAYWRIGHT_BROWSERS_PATH='D:/HermesData/cache/playwright-browsers' PLAYWRIGHT_EVIDENCE_DIR='<absolute-scratch-dir>' pnpm exec playwright test e2e/fixture-preview-r1.spec.ts --project=fixture-preview-chromium --retries=0
OBSERVATORY_DATA_SOURCE=mock pnpm run build
```

The committed-source browser drift case requires clean, tracked bound source files and committed reducer metadata. A dirty source correctly returns unavailable; do not erase that admission check to run the acceptance case. Windows browser storage is explicitly on D: per user request; Linux CI installs its pinned Chromium independently.

## Screenshot inventory
- `current-subject-drift.png`
- `dev-run-022-g5-waiting.png`
- `fixture-lab-replay-controls.png`
- `shared-prefix-empty.png`
- `shared-prefix-tree.png`
- `task-first-screen.png`
- `task-run-negative-020.png`
