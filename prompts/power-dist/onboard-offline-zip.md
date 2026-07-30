# DW SUPER Offline ZIP Onboarding Prompt

Use this prompt to install already-transferred DW SUPER Power ZIPs without network access.

## Objective

Onboard the selected Powers for one unambiguous target project using only local package files. DW-SuperApps owns the package store, inbox, cache, history, bindings, router, and host adapters. The selected project owns only its source, runtime roots, and project configuration.

GitHub, Git remotes, release downloads, and outbound Power acquisition are unavailable and must not be used.

## Resolve the workspace

Read, in order:

1. `AGENTS.md`;
2. `workspace.yaml`;
3. `docs/runbooks/POWER_DIST_ONBOARDING.md`;
4. `docs/PORTABLE_MULTI_HOST_ROUTER.md`;
5. target-project instructions, if present;
6. selected Power manifests under `manifests/powers/`.

Resolve these values from the workspace unless the user supplied an explicit value:

```text
WORKSPACE_ROOT = current DW-SuperApps checkout
STORE_ROOT     = workspace.yaml distribution.storeRoot, normally .dw/powers
INBOX_ROOT     = workspace.yaml distribution.inboxRoot, normally .dw/inbox/powers
PROJECT_ID     = one explicit or unambiguous enabled workspace product project
TARGET         = workspace project path for PROJECT_ID
POWERS         = PROJECT_ID projects[].powers.enabled, or the explicit user list
HOST           = configured host or all configured hosts
```

If more than one enabled project could be the target, stop with `BLOCKED_TARGET_AMBIGUOUS`. Do not silently choose the first project. `--target` selects the runtime target; it does not select the package store.

## Offline package contract

Search only in:

```text
DW-SuperApps/.dw/inbox/powers/<power-id>/
```

For every selected Power, require exactly one ZIP and its matching sidecar unless the user supplied an exact package and checksum path:

```text
.dw/inbox/powers/<power-id>/<package>.zip
.dw/inbox/powers/<power-id>/<package>.zip.sha256
```

Reject and report the corresponding `BLOCKED_*` result when the package is missing, multiple ZIPs are present, or the sidecar is missing. Preserve the inbox files after installation.

Before installation, verify that:

- the checksum sidecar contains the SHA-256 for the selected archive;
- the archive has one package root and an internal `MANIFEST.json`;
- the internal package ID matches `<power-id>`;
- every declared file exists with the declared size and SHA-256;
- declared entrypoints exist;
- `runtimeDataRoot` is relative, safe, and stays inside `TARGET`;
- archive members have no absolute path, parent traversal, or symlink;
- `STORE_ROOT` and `TARGET` do not overlap;
- an existing store package is managed before it is replaced;
- an existing `<TARGET>/.dw/powers/<power-id>` is recorded as `LEGACY_TARGET_INSTALL` and left byte-for-byte unchanged.

Do not acquire packages through Git, GitHub, release URLs, `curl`, `wget`, remote `power-dist`, or submodule initialization.

## Install

Run the package lifecycle sequentially for each selected Power so bindings and history remain unambiguous:

```bash
./bin/dw power install <power-id> \
  --source package \
  --package .dw/inbox/powers/<power-id>/<package>.zip \
  --checksum .dw/inbox/powers/<power-id>/<package>.zip.sha256 \
  --target <target-path>
```

The expected ownership split is:

```text
DW-SuperApps/.dw/powers/<power-id>/       installed package
DW-SuperApps/.dw/history/powers/<power-id>/ previous managed packages
DW-SuperApps/.dw/bindings/<project-id>/   target binding
DW-SuperApps/<host-adapter-roots>/        thin host routing
<target-path>/.gwc/                       GWC runtime/configuration
<target-path>/.ua/                        UA runtime/configuration
<target-path>/.task-me/                   Task Me runtime/configuration
<target-path>/.bmad/                      BMAD project configuration/output
```

Never create `<target-path>/.dw/powers`, copy package payloads into the target, or place host skill implementations in the target.

## Configure, activate, and validate

Configuration is optional unless the selected package contract requires it. If required, write it only under the package runtime root:

```bash
./bin/dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target <target-path>
```

Generate or refresh adapters only in DW-SuperApps:

```bash
./bin/dw host install all --mode wrapper
```

Run a real local Power invocation and the independent checks:

```bash
./bin/dw power sanity <power-id> --strict
./bin/dw power doctor <power-id> --target <target-path>
./bin/dw host status all
./bin/dw validate
./bin/dw doctor all --offline
python -m unittest discover -s tests -p "test_*.py"
```

Confirm that the installed package entrypoint resolves from `STORE_ROOT` before any source-submodule fallback, that bindings point to the installed package, that runtime/configuration exists only under declared target roots, and that no duplicate logical Power identity is visible across adapters.

## Report

Return one evidence table with `READY`, `PARTIAL`, `BLOCKED`, or `FAILED` for:

- package identity and checksum;
- manifest file sizes, hashes, and entrypoints;
- store and history;
- target binding and configuration;
- runtime preservation;
- host activation and dedupe;
- workspace and offline doctor;
- real invocation;
- legacy target detection;
- network discipline.

Also report the exact workspace root, store root, target path, selected project, selected Powers, package versions/source SHAs when present, changed paths, preserved inbox files, history paths, sanitized commands, and any unresolved warning. Explicitly confirm: `remote acquisition: SKIPPED_OFFLINE`.
