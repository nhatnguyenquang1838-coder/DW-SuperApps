# Implementation Plan

1. Pin the shared distribution workflow and schemas from Task 01.
2. Inventory the architect skill, its `references/**`, runbook, output contract, schemas, validation scripts, and host-neutral entrypoints.
3. Classify repository-specific sample/configuration material separately from reusable defaults.
4. Create an explicit allowlist recipe and deny all generated planning/runtime paths.
5. Add distributable default config and consumer binding templates.
6. Add reference-closure and forbidden-content tests.
7. Add provider workflow for main updates and manual stable-version publishing.
8. Smoke install into an empty application without running the skill.
9. Run `doctor` and verify no task folders, plan files, dashboard files, or external-system effects exist.
10. Record provider commit and release metadata for Task 05.
