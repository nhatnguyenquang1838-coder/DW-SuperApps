# Run-Level Impact Analysis

## Direct

- DW-SuperApps gains shared distribution contracts, builder, runtime, publishing, and final consumer integration.
- GWC and Task Me gain provider-owned skills-only packages.
- UA gains a controlled publishing boundary because upstream is read-only.
- Jira contains five Tasks and explicit Blocks links.

## Risks

- Accidental dashboard, historical evidence, task, plan, secret, cache, or runtime-data leakage.
- Missing transitive helpers referenced by skills.
- Cross-repository workflow drift.
- Silent UA upstream movement.
- Partial integration on the shared branch.

## Controls

Use allowlists, dependency-closure tests, one reusable workflow pinned by SHA, exact UA source lock, clean-install smoke tests, and a final merge/hygiene task.
