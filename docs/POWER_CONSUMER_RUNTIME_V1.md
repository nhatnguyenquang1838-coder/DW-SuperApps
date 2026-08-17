# DW Power Consumer Runtime v1

The consumer runtime separates the shared DW-SuperApps package store from project-owned runtime and project configuration.

## Ownership

```text
Workspace distribution store: DW-SuperApps/.dw/powers/<power-id>/
Workspace inbox:             DW-SuperApps/.dw/inbox/powers/<power-id>/
Workspace history:           DW-SuperApps/.dw/history/powers/<power-id>/
Workspace bindings:          DW-SuperApps/.dw/bindings/<project-id>/<power-id>.json
Project runtime:             <project>/.gwc | .ua | .task-me | .bmad
Project configuration:       <project>/<runtime-root>/config/
```

`--target` selects the project runtime target. `--store-root` overrides the workspace package store for tests or explicit external layouts.

## Source modes

| Mode | Behavior |
|---|---|
| `release` | Downloads a provider release ZIP and checksum using manifest templates. |
| `power-dist` | Downloads the provider distribution branch archive. |
| `package` | Installs a local validated package directory or ZIP. |
| `auto` | Uses `spec.distribution.defaultMode`. |
| `submodule` | Explicit compatibility/development source only; never a silent fallback. |

## Commands

```bash
dw power install task-me \
  --source package \
  --package .dw/inbox/powers/task-me/task-me.zip \
  --checksum .dw/inbox/powers/task-me/task-me.zip.sha256 \
  --target projects/rental-home

dw power configure task-me --config ./config.yaml --contract ./contract.yaml --target projects/rental-home
dw power sanity <power-id>
dw power doctor task-me --target projects/rental-home
dw power history task-me
dw power rollback task-me --version <version>
dw power uninstall task-me --target projects/rental-home
```

Expected result:

```text
DW-SuperApps/.dw/powers/task-me/
projects/rental-home/.task-me/
DW-SuperApps/.dw/bindings/rental-home/task-me.json
```

Normal lifecycle commands must not create `projects/rental-home/.dw/`.

## Install/availability vs activate/use

Installation makes a Power *available* to a project (declared by `workspace.yaml` `powers.enabled`). Activation and use are a separate **task-intent** decision: an installed Power is not automatically run. Load only the Powers the current task requires; installed-but-unneeded Powers stay available but inactive. The managed package under `DW-SuperApps/.dw/powers/<power-id>/` is the execution surface — the Power's upstream source submodule is an explicit compatibility/development fallback only, never the default.

## Target project submodule vs Power source submodule

A project task works against the **target product submodule** (e.g. `projects/rental-home`); its parent gitlink pin is not the task execution head and must not be bumped implicitly. The **Power source submodule** (e.g. `projects/ua` → `Understand-Anything`) is upstream Power code, not a project runtime target. Do not execute or initialize the Power source submodule during normal managed onboarding.

## Split lifecycle behavior

- **Install:** writes package code to the workspace store and creates only the declared runtime root in the project.
- **Configure:** writes managed configuration below the project runtime root and updates the workspace binding.
- **Doctor:** validates store, package integrity, binding, runtime, configuration, and legacy detection separately.
- **History:** lists workspace package history and does not require a target.
- **Rollback:** replaces the shared managed package from workspace history and refreshes bindings.
- **Uninstall:** detaches the selected project target; preserves runtime by default; removes the shared package only when no bindings remain.

## Legacy detection

Existing `<project>/.dw/powers/<power-id>` paths are reported as `LEGACY_TARGET_INSTALL`. They are never overwritten, deleted, migrated, or used as an execution fallback by normal onboarding.

## Safety rules

- ZIP extraction rejects absolute paths, parent traversal, and symlinks.
- Package identity must match the requested manifest.
- Every declared file is size- and SHA-256-verified.
- Store and runtime target must not overlap.
- Distribution roots must not resolve inside the project target.
- Unmanaged packages and runtime configuration are never overwritten or removed.
- Shared package removal is blocked by remaining bindings.
- Runtime removal requires `--include-runtime --yes`.
