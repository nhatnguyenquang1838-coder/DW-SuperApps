# Implementation Plan

1. Pin the merged DW-PDIST-01 reusable workflow SHA and contract version.
2. Inventory references from `skills/gwc-g1/SKILL.md`, `AGENTS.md`, and `agents/chatgpt-agent/agent-instructions.md`.
3. Resolve referenced contracts, schemas, templates, runbooks, and validators; classify required versus optional.
4. Create `distribution/power-package.yaml` using explicit file or narrow-directory allowlists.
5. Add config defaults, example config, and a default consumer authority contract.
6. Add recipe validation tests proving required entrypoints are included and forbidden content is excluded.
7. Add `.github/workflows/publish-power.yml` for `main` and manual triggers.
8. Add clean consumer installation tests for configured hosts and CLI discovery.
9. Assert `.gwc` is empty after install and that no gate/task/envelope is created.
10. Record the resulting release asset names and `power-dist` branch contract for Task 05.
