# PR #130 — code remediation R2

Recorded: 2026-10-30T17:28:44.652838+00:00

Status: **code safety/UI repairs verified; NOT full semantic certification or independent approval**. PR stays Open/Draft. No merge, deployment, production migration/data operations or `.gwc` changes.

## Source binding

- Repository: `nhatnguyenquang1838-coder/DW-SuperApps`
- Branch: `integration/SCRUM-820-dwo-v2`
- Baseline HEAD: `71463bcd8e100f0ebea23d19cce65f009289ecf0`
- 39 changed source/test/config files are bound by `source-manifest.json` (LF-normalized SHA-256). The final delivery SHA is recorded in the PR body; a commit cannot embed its own SHA.
- Original checkout stays on `main` at `0f78638a9db7644c0b4e4f6fcd1b1c9ae0b760d0`.
- Original fixture pack and legacy R1 screenshots/manifests were not rewritten. This directory is the new remediation evidence.

## Repairs

1. LangGraph no longer trusts supplied semantic PASS flags or self-digested candidate facts. Integrity and subject/source/contract binding are checked; absent an independent canonical source verifier, all required semantic checks remain UNKNOWN with `SEMANTIC_SOURCE_VERIFIER_UNAVAILABLE`. This is a safety repair, not a replacement semantic engine.
2. Fixture events are validated and folded through `reduceEventPrefix`; catalog topology does not fabricate observed facts. Empty prefixes retain UNKNOWN/null facts and no canonical history. Legacy CANCELLED/SUPERSEDED source markers remain separate from canonical gate states.
3. Recursive hierarchy includes 017 → 018 → 019, atomic markers, parent validation, cycle/duplicate guards, selection, collapse/expand and keyboard navigation. Dependency edges are separate from hierarchy and not implicitly SATISFIED.
4. One parent ReplaySession drives actual workspace prefix, graph/card facts, inspector and player controls. Scenario/reset remounts reset selection and arrival bookkeeping. Unbound full-tip evidence is not projected into arbitrary prefixes. Tests compare client/server reducer facts at every prefix of all 29 conforming scenarios; the incompatible 020 remains outside reducer input.
5. Browser testing reproduced and fixed canvas overflow intercepting player clicks and the legacy graph adapter dropping canonical gate facts. Cards no longer show a fabricated FUTURE state; layout groups remain UNKNOWN rather than pretending to be canonical gate instances. No force-click was used.
6. Production middleware denies all `/dev/*` entrypoints. Receipt projection requires an independently computed current subject; it no longer echoes the receipt digest as proof. Playwright uses a portable Node launcher, cold start and exactly one source server/project per invocation.

## Real execution evidence

| Check | Observed result |
|---|---|
| Full Vitest regression, threads max/min workers=1 | 76 files / 1,044 tests passed |
| Follow-up after hook-dependency-only cleanup | 4 files / 39 tests passed |
| Application typecheck | passed |
| Test-code typecheck | **0 diagnostics**, not merely exit zero against the historical baseline 86 |
| Python suite with installed LangGraph and SQLite checkpointer | 155 tests + 4 subtests passed; 0 failures/errors/skips in JUnit |
| Playwright Chromium cold start, final source | 5 passed (39.1s), retries=0; six screenshots |
| Next.js production build, mock source to avoid live data | passed |
| Local production HTTP ingress with fixture override | 8 `/dev` paths returned 404, no fixture badge; `/tasks` returned 200 with source-unavailable notice and no fixture badge |

The full regression preceded a hook-dependency-only lint cleanup; the affected 39 tests, both typechecks, browser suite and production build were then rerun on the final source. ANSI/trailing-whitespace-normalized final logs are under `verification/`; the raw originals remain in the task scratch directory. Browser `pageerror` collection in the shared-prefix case was empty. Production probes are against **localhost**, not a deployment or production service. The owned local production server was stopped after probes.

## Reproduction

From `projects/dw-observation` with dependencies installed:

```bash
./node_modules/.bin/vitest run --pool=threads --maxWorkers=1 --minWorkers=1
npm run typecheck
npm run typecheck:tests:strict
python -m pytest tests -q
PLAYWRIGHT_BROWSERS_PATH='D:/HermesData/cache/playwright-browsers' \
PLAYWRIGHT_EVIDENCE_DIR='<absolute-scratch-evidence-dir>' \
./node_modules/.bin/playwright test e2e/fixture-preview-r1.spec.ts --project=fixture-preview-chromium --retries=0
OBSERVATORY_DATA_SOURCE=mock npm run build
```

Use the installed isolated Python interpreter with LangGraph/checkpoint-sqlite, not an unconfigured system Python. The D: browser cache is the user-requested Windows location; other hosts may choose another cache consistently for install and execution. The HTTP probe output contains its exact localhost paths and environment.

## Remaining boundaries / blockers

- **Full semantic qualification remains open:** no independently admitted canonical source-artifact verifier exists. UNKNOWN must not be reported as QUALIFIED.
- **Current fixture qualification remains UNKNOWN/CURRENT_SUBJECT_UNAVAILABLE:** the checked-out reducer has no authoritative `DWO_REDUCER_VERSION` declaration. An invented hash-version is not accepted as version identity.
- **Independent Pattern E is INCONCLUSIVE, not PASS:** fresh per-profile smoke with the main-session model pins was rejected by gateway resume/session policy (`creation overrides are unsupported on resume`). No cheaper profile-model fallback was used and no gateway restart was claimed. Resume after a supported fresh per-profile launch preserving the requested model is verified.
- GitHub reviewer request is unresolved: current collaborators list contains only the PR author; the earlier bot login was not resolvable. No self-review/request success is claimed.
- `.gwc/tasks/SCRUM-820-T13/g0/context-snapshot.yaml` provenance disposition is untouched; it requires a separately authorized correction. No review threads were automatically resolved.
- Existing advisory warnings remain: unsupported `devIndicator` in Next config; a missing hook dependency in `components/login-epic/RuntimeGraphCanvas.tsx`; Node test localStorage/act warnings and Python dependency deprecation warnings. No new UnifiedRunWorkspace hook warning remains.
- Mock navigation/visual snapshot suite and Linux screenshot baselines were not certified in this fixture-specific browser run. The original unknown-task negative test was preserved and the worker's broad Linux skip was removed rather than masking those checks.

## Screenshot inventory

- `task-first-screen.png`
- `fixture-lab-replay-controls.png`
- `dev-run-022-g5-waiting.png`
- `task-run-negative-020.png`
- `shared-prefix-tree.png`
- `shared-prefix-empty.png`
