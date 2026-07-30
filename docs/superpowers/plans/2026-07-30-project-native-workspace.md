# Project-native workspace registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the migration from the duplicated top-level `systems[]` registry to project-native target configuration across runtime, installation, distribution, doctor, templates, documentation, and tests.

**Architecture:** Add one lightweight project-target resolver for registered product/runtime projects. All command paths use it; compatibility command names remain read-only aliases. Keep packages, bindings, history, cache, and adapters in the workspace store, and keep only declared runtime/configuration under the project target.

**Tech Stack:** Python 3, PyYAML, unittest, JSON/YAML manifests, Bash launchers.

## Global Constraints

- `projects[]` is the only canonical repository and runtime-target registry.
- Generated and offline workspaces must not contain a `systems` key.
- Existing binding directory names and `systemId` JSON keys remain stable, with project-derived values.
- Existing target-local `.dw/powers` installations are reported as `LEGACY_TARGET_INSTALL` and preserved.
- Distribution roots must not overlap or resolve inside a project target.
- Do not modify unrelated pre-existing `.ua/intermediate` or submodule changes.
- Do not activate or use the GWC Power for this migration.

---

### Task 1: Add the shared project-target resolver and registry contract

**Files:**
- Create: `scripts/dw_project_targets.py`
- Modify: `scripts/dw_project_registry.py`
- Modify: `scripts/dw_project_add.py`
- Test: `tests/test_project_registry.py`

**Interfaces:**
- `runtime_projects(workspace: dict[str, Any]) -> list[dict[str, Any]]`
- `find_runtime_project(workspace: dict[str, Any], project_id: str) -> dict[str, Any]`
- `enabled_powers(project: dict[str, Any]) -> list[str]`
- `project_path(project: dict[str, Any], root: Path) -> Path`

- [ ] **Step 1: Write failing tests for project-native target lookup and clean templates.**

  Replace registry fixtures that require `systems[]` with a product project containing `powers.enabled`; assert `find_runtime_project` and `enabled_powers` return the project-native values. Assert `template_workspace` has no `systems` key and uses `project-owned` data ownership.

- [ ] **Step 2: Run the focused registry tests and verify the legacy assumptions fail.**

  Run: `python3 -m unittest tests.test_project_registry -v`

  Expected: failures in the old template and offline registration assertions, plus the new resolver tests failing until the implementation exists.

- [ ] **Step 3: Implement the resolver and registry validation.**

  Define target roles as `product` and `runtime-target`; reject a `systems` key with an actionable migration error; validate nested `powers.enabled` as a string list; validate top-level Power references through their `project` entry without requiring duplicated `path` or `source`; generate project-native templates; and make project add place `powers.enabled` under the project when `--enable-powers` is supplied.

- [ ] **Step 4: Update the project-add CLI contract.**

  Keep `--system` and `--system-id` accepted as deprecated aliases for compatibility, but map them to the project’s product role and nested `powers.enabled`; reject attempts to create a second registry entry; allow offline registration for an existing product project without writing `systems`.

- [ ] **Step 5: Run the focused registry tests and commit the self-contained change.**

  Run: `python3 -m unittest tests.test_project_registry -v`

  Commit only the resolver, registry, project-add implementation, and registry tests with `git add scripts/dw_project_targets.py scripts/dw_project_registry.py scripts/dw_project_add.py tests/test_project_registry.py && git commit -m "refactor: resolve runtime targets from projects"`.

### Task 2: Migrate CLI, orchestration, reporting, and cleanup

**Files:**
- Modify: `scripts/dw_cli.py`
- Modify: `scripts/dw_orchestrator.py`
- Modify: `scripts/dw_report.py`
- Modify: `scripts/dw_entry.py`
- Modify: `scripts/clean_power_setup.py`
- Test: `tests/test_power_runtime_v2.py`
- Test: `tests/test_workspace_distribution_routing.py`
- Test: `tests/test_clean_power_setup.py`

**Interfaces:**
- `dw_cli.find_system()` remains a deprecated alias that delegates to `find_runtime_project()`.
- `dw_cli.system_list()` renders runtime projects and nested enabled Powers.
- `dw_cli.system_powers()` renders nested project configuration while preserving command output fields.
- Orchestration and report target lookup use the same resolver and nested `orchestration` block.

- [ ] **Step 1: Add failing CLI and orchestration tests.**

  Assert `workspace info` reports runtime projects, `dw system list` and `dw system powers rental-home` work against nested project configuration, `select_submodules("systems")` returns project-derived compatibility entries, and orchestration/report lookup works when `systems` is absent.

- [ ] **Step 2: Run the focused CLI/cleanup tests to capture the current failures.**

  Run: `python3 -m unittest tests.test_power_runtime_v2 tests.test_workspace_distribution_routing tests.test_clean_power_setup -v`

- [ ] **Step 3: Replace direct `systems[]` reads with the shared resolver.**

  Resolve Power source paths from `powers[].project` and `projects[]`; derive runtime target paths from project entries; have compatibility aliases return project-derived rows; and make `dw_entry` cleanup enumerate runtime projects while keeping its confirmation and safety checks.

- [ ] **Step 4: Update generated host/discovery text.**

  Replace stale “target system” routing instructions in `dw_cli` and `dw_workspace_dist` generated content with “runtime target project” wording while retaining user-facing compatibility command examples only where needed.

- [ ] **Step 5: Run focused tests and commit.**

  Run: `python3 -m unittest tests.test_power_runtime_v2 tests.test_workspace_distribution_routing tests.test_clean_power_setup -v`

  Commit with `git add scripts/dw_cli.py scripts/dw_orchestrator.py scripts/dw_report.py scripts/dw_entry.py scripts/clean_power_setup.py tests/test_power_runtime_v2.py tests/test_workspace_distribution_routing.py tests/test_clean_power_setup.py && git commit -m "refactor: route runtime commands through projects"`.

### Task 3: Migrate offline setup, release distribution, and doctor paths

**Files:**
- Modify: `scripts/offline_release_installer.py`
- Modify: `scripts/dw_workspace_dist.py`
- Modify: `scripts/dw_power_store/common.py`
- Modify: `templates/full-distribution/workspace-template.yaml`
- Modify: `scripts/validate-workspace.py`
- Test: `tests/test_full_distribution_release.py`
- Test: `tests/test_power_package_consumer.py`
- Test: `tests/test_power_runtime_installer.py`

**Interfaces:**
- `register_project(...) -> tuple[data, target, project_id]` registers one project and nested Power configuration.
- `validate_setup_registry(...)` rejects a legacy `systems` key and validates project-native targets.
- `dw_workspace_dist.find_runtime_project()` resolves orchestration from project entries.
- Binding paths remain `.dw/bindings/<project-id>/<power-id>.json`.

- [ ] **Step 1: Add failing offline/full-distribution assertions.**

  Assert generated workspace YAML has no `systems`, setup registration writes `projects[project].powers.enabled`, full-distribution setup validation passes after doctor, and repair never recreates a stale `systems` registry.

- [ ] **Step 2: Run the focused release and consumer tests.**

  Run: `python3 -m unittest tests.test_full_distribution_release tests.test_power_package_consumer tests.test_power_runtime_installer -v`

- [ ] **Step 3: Migrate setup registration and validation.**

  Remove `systems` parsing and generation; require product/runtime roles; merge enabled Powers into `project.powers.enabled`; preserve existing project orchestration; use project ID for binding paths and `systemId` compatibility fields; and make repair back up malformed legacy files before replacing them with a project-native template.

- [ ] **Step 4: Migrate distribution host orchestration lookup and validation.**

  Replace the hard-coded `rental-home` system lookup with the first matching runtime project or a project resolver; keep package-store/runtime separation and managed-marker checks; ensure `validate-workspace` computes target roots from project roles and nested enabled Powers.

- [ ] **Step 5: Run focused release/consumer tests and commit.**

  Run: `python3 -m unittest tests.test_full_distribution_release tests.test_power_package_consumer tests.test_power_runtime_installer -v`

  Commit with `git add scripts/offline_release_installer.py scripts/dw_workspace_dist.py scripts/dw_power_store/common.py templates/full-distribution/workspace-template.yaml scripts/validate-workspace.py tests/test_full_distribution_release.py tests/test_power_package_consumer.py tests/test_power_runtime_installer.py && git commit -m "refactor: make offline distribution project-native"`.

### Task 4: Align documentation and generated workspace surfaces

**Files:**
- Modify: `docs/runbooks/POWER_DIST_ONBOARDING.md`
- Modify: `docs/DW_SUPER_SETUP.md`
- Modify: `docs/POWER_RUNTIME_V2.md`
- Modify: `docs/MULTI_HOST_SETUP.md`
- Modify: `docs/PORTABLE_MULTI_HOST_ROUTER.md`
- Modify: `docs/installation/ADD_PROJECT.md`
- Modify: `docs/installation/INSTALL_POWERS.md`
- Modify: `docs/installation/OFFLINE_INSTALL.md`
- Modify: `prompts/power-dist/onboard.md`
- Modify: `prompts/power-dist/onboard-offline-zip.md`
- Modify: `templates/full-distribution/workspace-template.yaml`

- [ ] **Step 1: Replace schema examples and commands.**

  Document `projects[].powers.enabled`, `projects[].orchestration`, `--target projects/<project-id>`, workspace-owned package/binding roots, and the deprecated `dw system` aliases. Remove instructions that require creating or editing `systems[]`.

- [ ] **Step 2: Search the repository for stale authoritative references.**

  Run: `rg -n 'systems:|systems\[|system-owned|enabled_powers' scripts templates docs prompts tests --glob '*.py' --glob '*.yaml' --glob '*.yml' --glob '*.md'`

  Remaining matches must be limited to compatibility field names, historical migration text, test fixture path names, or explicitly deprecated command names.

- [ ] **Step 3: Run documentation/template checks and commit.**

  Run: `git diff --check`

  Commit with `git add docs prompts templates/full-distribution/workspace-template.yaml && git commit -m "docs: describe project-native workspace targets"`.

### Task 5: Full verification and handoff

**Files:**
- Test: all `tests/test_*.py`
- Inspect: complete branch diff and user-owned pre-existing changes

- [ ] **Step 1: Run the complete unit suite.**

  Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

- [ ] **Step 2: Run workspace validation and offline doctor.**

  Run: `./bin/dw validate` and `./bin/dw doctor all --offline`.

- [ ] **Step 3: Verify no target distribution leakage.**

  Check that no new `projects/*/.dw/powers`, target host adapters, or package payloads were created, and that bindings still resolve to workspace `.dw/bindings/<project-id>/`.

- [ ] **Step 4: Review the complete diff and status.**

  Run: `git diff --check`, `git diff --stat`, `git diff --name-status`, and `git status --short --branch`; confirm the pre-existing `.ua/intermediate` and `projects/gwc` changes remain unstaged and untouched.

- [ ] **Step 5: Report exact evidence and remaining boundaries.**

  Report branch, base/head SHAs, changed files, test commands/results, package-store/runtime ownership, compatibility aliases, preserved legacy detections, and any unrun real Power invocation. Do not claim `READY` for runtime installation unless configuration, host activation, doctor, and invocation all pass.
