# Project-native workspace registry design

## Decision

`projects[]` is the only canonical repository and runtime-target registry. The
top-level `systems[]` key is removed from the schema and must not be generated,
read, or required by workspace tooling.

The existing `dw system list` and `dw system powers <id>` commands remain as
deprecated compatibility aliases for one release. They resolve product/runtime
projects and read their nested `powers.enabled` configuration; they do not read
or recreate a `systems[]` section. Existing binding JSON keeps its `systemId`
field and directory layout for stable on-disk compatibility, but the value is
derived from the registered project ID.

## Configuration model

Product/runtime projects use:

```yaml
projects:
  - id: rental-home
    path: projects/rental-home
    source: owner/rental_home
    roles: [product]
    powers:
      enabled: [gwc, ua, task-me, bmad]
    orchestration:
      primary: gwc
      workers: [task-me, bmad, ua]
      hooks: []
```

Power source metadata remains in `projects[]`; top-level `powers[]` only
references the source project with `id`, `project`, and `enabled`. Distribution
roots remain workspace-owned under `distribution`, and runtime roots remain
project-local under `data_ownership.roots`.

## Components and flow

- `dw_project_registry` validates project identity, roles, Power references,
  nested enabled-Power configuration, and generates project-native templates.
- `dw_cli`, `dw_orchestrator`, and `dw_report` resolve a target with the same
  project resolver. Status, orchestration, and reports use nested project data.
- `dw_power_store.common` derives binding IDs from product/runtime projects and
  preserves the package-store/runtime split and legacy-target detection.
- `validate-workspace`, `clean_power_setup`, and `dw_entry` derive target
  projects from roles and guard distribution/runtime boundaries without a
  systems registry.
- `offline_release_installer` registers the project, nested Powers, and
  orchestration directly. It emits no `systems` key and keeps bindings under
  the project ID.
- `dw_workspace_dist` resolves workspace package paths and host adapters without
  target registry duplication.
- Full-distribution and workspace-init templates use the same clean schema.

The target lifecycle remains:

```text
project config -> workspace package store -> project runtime -> binding
               -> host adapter -> doctor/status/report
```

No package payload, host adapter, or `.dw` distribution directory is created
inside a product project. Existing target-local legacy installs are reported
and preserved.

## Errors and compatibility

Malformed or legacy workspaces fail closed with a message directing the user to
move target configuration into `projects[].powers` and
`projects[].orchestration`. Unknown target projects, Powers, duplicate IDs,
unsafe paths, and store/runtime overlap remain errors. The compatibility CLI
aliases return project-derived data and never silently synthesize legacy YAML.

## Verification

Tests cover project-native validation and templates, project add/bootstrap,
compatibility CLI aliases, orchestration/report resolution, cleanup target
selection, offline release setup/repair, full-distribution validation, stable
bindings, legacy target preservation, and the existing package-store/runtime
safety checks. The required completion checks are the focused migration tests,
the full unittest suite, `./bin/dw validate`, `./bin/dw doctor all --offline`,
and `git diff --check`.
