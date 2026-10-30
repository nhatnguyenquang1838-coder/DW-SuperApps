# R3 CI recovery — hosted context validation

This addendum supersedes only the final-head/source-manifest expectation for the original `.preview-evidence/remediation-r3` snapshot at5481fdf2. Preserve that pack as historical Windows runtime evidence; do not relabel it as the current CI run.

## Reproduced failure and correction

Actual hosted run https://github.com/nhatnguyenquang1838-coder/DW-SuperApps/actions/runs/41143629937 failed before any job: job-level env at lines18/19 cannot use `runner.temp`. Earlier local YAML/Bash parsing and9 contract tests did not validate GitHub expression-context availability. Initial source-only reviewer PASS at5481fdf2 is not proof of hosted CI validity and will not be used as the final-head review.

- RED: actual GitHub annotation; actionlint1.7.12 rejected both unavailable runner contexts, exit1; new regression failed1/10 against unchanged workflow, normal Vitest exit1.
- Minimal correction: remove job-level runner expressions. First Bash step exports TMPDIR and DWO_R3_SCRATCH_ROOT from real `$RUNNER_TEMP` through `$GITHUB_ENV`. Later steps inherit the same trusted runner scratch path.
- GREEN: actionlint target workflow exit0 (expression validation enabled; optional shellcheck/pyflakes not installed), contract10/10 passed and strict test typecheck errors0/baseline0/delta+0. actionlint Windows archive checksum was verified against the release checksum file before execution; this is not a signing/authenticity claim beyond the HTTPS release source.
- Only workflow and its regression test changed; reducer/reader/routes/Python/fixture/receipt/contract/.gwc bytes remain unchanged. `source-manifest.json` records the nine cumulative R3 source blobs including these two updates; original R3 source-manifest stays bound to its own snapshot, not this new workflow.
- All6 Chromium cases passed on clean5d2bf767 code source; an additional actual cross-route DRIFTED case passed at clean5481fdf2 after the evidence commit. The7 core runtime blobs in this recovery are unchanged. Fresh final-head reviews and hosted execution are separate results published in the PR body after this additive commit.

No new local full-suite/build/Python run is claimed for this workflow-only correction. Initial local full run77/1056, Python155+4, browser6 and production build/ingress evidence retain their original source binding. The new hosted full-suite count must be read from the actual final-head logs; the new contract count is10.

## Authority and remaining limits

Qualification remains UNKNOWN without the independent canonical semantic source-artifact verifier (`SEMANTIC_SOURCE_VERIFIER_UNAVAILABLE`). Historical receipts are not requalified. dwo.reducer/2 is a NEW published implementation identity, not a recovery of a historical receipt claim. No authority/lifecycle mutation, .gwc correction, merge, deploy, production-data access, baseline increase, skipped/empty Python acceptance or CI error suppression is introduced.

Final exact-head hosted CI links, independent Pattern E model/provider/fallback/session readback and structured verdicts belong to the PR target. They must not be represented by static local parsing, old PASS or a smoke probe. Local production denial proves localhost isolation only; no release/deployed ingress or OS pixel-baseline certification is claimed.
