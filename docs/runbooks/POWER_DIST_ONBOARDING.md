# Power Dist Onboarding Runbook

## Purpose

Use this runbook to install, update, configure, activate, validate, doctor, repair, or invoke DW SUPER Powers for a registered product project or an explicitly external consumer.

The required lifecycle is:

```text
DISCOVER -> PREFLIGHT -> INSTALL -> CONFIGURE -> ACTIVATE -> DOCTOR -> USE -> REPORT
```

Do not report `READY` unless installation, required configuration, host activation, doctor checks, and one real invocation pass.

## Ownership model

DW-SuperApps is the distribution and host-control owner. The selected product project is the runtime and project-configuration owner.

| Asset | Owner |
|---|---|
| Installed Power packages | `DW-SuperApps/.dw/powers/` |
| Package inbox | `DW-SuperApps/.dw/inbox/powers/` |
| Package cache | `DW-SuperApps/.dw/cache/` |
| Package history | `DW-SuperApps/.dw/history/powers/` |
| Package bindings | `DW-SuperApps/.dw/bindings/` |
| Router and host adapters | DW-SuperApps |
| GWC runtime/configuration | `<project>/.gwc/` |
| UA runtime/configuration | `<project>/.ua/` |
| Task Me runtime/configuration | `<project>/.task-me/` |
| BMAD project configuration/output | `<project>/.bmad/`, `_bmad/`, `_bmad-output/` |

Normal onboarding must not create `<project>/.dw/` or host skill payloads inside a registered project.

## Related documents

- Global rules: `AGENTS.md`
- Consumer runtime: `docs/POWER_CONSUMER_RUNTIME_V1.md`
- Portable host design: `docs/PORTABLE_MULTI_HOST_ROUTER.md`
- Online/general prompt: `prompts/power-dist/onboard.md`
- Offline ZIP prompt: `prompts/power-dist/onboard-offline-zip.md`
- Workspace registry: `workspace.yaml`
- Power manifests: `manifests/powers/<power-id>.yaml`

## Resolve inputs

Resolve available information instead of asking the user to repeat it.

1. **Workspace root:** current `DW-SuperApps` checkout.
2. **Distribution store:** `workspace.yaml > distribution.storeRoot`, default `.dw/powers`.
3. **Target project:** explicit user target; otherwise matching product/runtime project in `workspace.yaml`; otherwise the only configured runtime project; otherwise `BLOCKED_TARGET_AMBIGUOUS`.
4. **Runtime target:** the selected project `path`, or an explicitly supplied external consumer path.
5. **Powers:** explicit list; otherwise the project's `powers.enabled`.
6. **Host:** explicit host; otherwise detect the current IDE/agent host.
7. **Source priority:** explicit package; valid workspace inbox ZIP; manifest `defaultMode`; explicit source-submodule mode only for migration or development.

`--target` always identifies the project runtime target. It does not select the package store.

`--store-root` overrides only the workspace package store and is intended for tests or explicit external workspace layouts. Relative values resolve from DW-SuperApps. The store must not overlap or resolve inside the runtime target.

## Source of truth

Read and reconcile:

1. local checkout and exact local HEAD;
2. root and target `AGENTS.md` files;
3. `workspace.yaml` distribution and project declarations;
4. selected Power manifests;
5. distribution evidence when present;
6. supplied ZIP/checksum and internal `MANIFEST.json`;
7. installed `.dw/powers/<power-id>/MANIFEST.json`;
8. applicable runtime and host documentation.

When online, verify the current default branch and exact `main` SHA. When explicitly offline, record remote verification as `SKIPPED_OFFLINE`.

If package identity, version, checksum, manifest, entrypoint, binding, or recorded evidence conflict, report `BLOCKED_DISTRIBUTION_DRIFT`.

## Preflight

Before installation:

1. detect OS, shell, Python, Git, current host, and Node/npm when BMAD is selected;
2. verify the workspace root, store root, and runtime target;
3. inspect workspace `.dw/inbox`, `.dw/powers`, `.dw/history`, `.dw/bindings`, router, and host adapters;
4. inspect target runtime roots;
5. detect `<target>/.dw/powers/<power-id>` as `LEGACY_TARGET_INSTALL`;
6. preserve legacy installations and existing runtime data;
7. refuse unsafe overlap, traversal, symlinks, identity mismatch, or unmanaged overwrite;
8. record pre-install state.

Do not initialize Power submodules during normal package onboarding.

## Online installation

Run package lifecycle commands from the DW-SuperApps root:

```bash
./bin/dw power install <power-id> \
  --source auto \
  --target projects/<project-id>
```

The expected split is:

```text
DW-SuperApps/.dw/powers/<power-id>/
projects/<project-id>/<runtime-root>/
DW-SuperApps/.dw/bindings/<project-id>/<power-id>.json
```

For an isolated test or external store layout:

```bash
./bin/dw power install <power-id> \
  --source package \
  --package /path/to/package.zip \
  --checksum /path/to/package.zip.sha256 \
  --store-root /external/workspace/.dw/powers \
  --target /external/project
```

## Offline ZIP inbox

Offline packages belong to the workspace inbox:

```text
DW-SuperApps/
└── .dw/
    ├── inbox/
    │   └── powers/
    │       ├── gwc/
    │       ├── ua/
    │       ├── task-me/
    │       └── bmad/
    ├── powers/
    ├── cache/
    ├── history/powers/
    └── bindings/
```

Never use `<project>/.dw/inbox/powers` for normal workspace-managed onboarding.

For each selected Power:

1. scan `.dw/inbox/powers/<power-id>/`;
2. require one ZIP and matching `.zip.sha256` unless an exact path is supplied;
3. identify packages using internal `MANIFEST.json`;
4. verify package identity;
5. verify the archive checksum;
6. verify every declared file size and SHA-256;
7. reject absolute paths, parent traversal, archive symlinks, and unmanaged overwrite;
8. install with `--source package`;
9. preserve the inbox files;
10. continue through configuration, host activation, doctor, and invocation.

```bash
./bin/dw power install <power-id> \
  --source package \
  --package ".dw/inbox/powers/<power-id>/<package>.zip" \
  --checksum ".dw/inbox/powers/<power-id>/<package>.zip.sha256" \
  --target "projects/<project-id>"
```

During offline mode, do not run Git pull/fetch/clone, release download, `curl`, `wget`, remote `power-dist`, or submodule initialization for Power acquisition.

## Configuration and bindings

Configuration belongs under the selected runtime root, not under `<project>/.dw/config`.

```bash
dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target projects/<project-id>
```

Expected configuration path:

```text
projects/<project-id>/<runtime-root>/config/
```

The workspace binding records the target, installed package path, package version/digest, runtime root, and configuration state.

Never invent credentials, secrets, or external authority. Optional missing configuration is `optional-missing`, not failure.

## Host activation

Generate adapters only in DW-SuperApps:

```bash
./bin/dw host install all --mode wrapper
```

Resolution order:

```text
DW-SuperApps/.dw/powers/<power-id>/MANIFEST.json entrypoint
  -> explicit source-submodule fallback when no managed package exists
```

Host adapters must not resolve `<project>/.dw/powers`. Projects receive no Power skill payloads.

The current runtime may still generate one adapter per Power. Treat that as a compatibility layer until the canonical `dw-super` router is implemented.

## BMAD handling

BMAD has two ownership phases:

1. **Workspace phase:** package code, package manifest, host skills, and host bootstrap markers remain in DW-SuperApps.
2. **Project phase:** `.bmad`, `_bmad`, `_bmad-output`, and project-specific configuration are created in the target project only when declared and required.

Do not install the BMAD website, dashboard, repository tests, evals, or generated web bundles.

## Legacy target installations

Probe:

```text
<project>/.dw/powers/<power-id>
<project>/.dw/history/
<project>/.dw/inbox/powers/
```

When present:

```yaml
legacy:
  status: LEGACY_TARGET_INSTALL
  action: preserved
```

The workspace package wins for execution. Do not overwrite, delete, migrate, or silently execute the legacy package. Cleanup is outside normal onboarding.

## Doctor matrix

Doctor must report independent layers:

| Layer | Required result |
|---|---|
| Workspace | `workspace.yaml` distribution paths are valid |
| Source | Online distribution or explicit local package mode is valid |
| Integrity | Package identity, sizes, and hashes pass |
| Store | `.dw/powers/<power-id>` is managed |
| Binding | Target-to-package binding is managed and current |
| Runtime | Declared target runtime root exists |
| Configuration | Required target runtime configuration is managed |
| Host | Workspace adapter resolves the workspace package store first |
| Dedupe | No duplicate logical Power identity is visible |
| Legacy | Legacy target installs are reported and preserved |
| Safety | No target `.dw` creation, traversal, overlap, or unmanaged overwrite |
| Network discipline | No remote acquisition during offline mode |

Use statuses exactly:

- `READY`: installation, required configuration, activation, doctor, and invocation pass;
- `PARTIAL`: package is valid but configuration, routing, activation, or invocation is incomplete;
- `BLOCKED`: a required dependency, authority, safe path, or unambiguous source is unavailable;
- `FAILED`: an executed operation returned a real failure.

## History, rollback, and uninstall

Package history and rollback are workspace-store scoped:

```bash
dw power history <power-id>
dw power rollback <power-id> --version <version>
```

Rollback updates workspace package bindings and does not delete project runtime data.

Uninstall detaches the selected project target first:

```bash
dw power uninstall <power-id> --target projects/<project-id>
```

- managed target configuration is removed;
- runtime is preserved by default;
- the shared package remains while another binding exists;
- the shared package is removed only when no bindings remain;
- destructive runtime removal requires `--include-runtime --yes`;
- legacy target installations remain untouched.

## Required validation

Run:

```bash
python -m unittest discover -s tests -p "test_*.py"
./bin/dw validate
./bin/dw doctor all --offline
```

Additionally verify:

```text
no new projects/<project>/.dw/
no host adapter under projects/<project>/
workspace package entrypoint is preferred
runtime/configuration exists only in declared project roots
legacy target artifacts are byte-for-byte unchanged
```

## Completion report

Return:

- workspace root, distribution store, runtime target, and runtime root;
- detected environment and source mode;
- exact package version, source SHA when available, package path, and checksum;
- binding, configuration, host adapter, doctor, dedupe, and invocation results;
- created or changed paths;
- sanitized commands;
- history, rollback, detach, and uninstall behavior;
- legacy detections and unresolved risks;
- one evidence table using `READY`, `PARTIAL`, `BLOCKED`, or `FAILED`.
