# Offline Distribution Release Runbook

## Purpose

Replace branch-based offline distribution with source-built, tag/download-only release artifacts.

The aggregate release workflow is `.github/workflows/publish-full-distribution-release.yml`. It runs on
`dw-superapps-v*` tags or manual dispatch, builds `gwc`, `ua`, `task-me`, and `bmad` from the checked-out
source pins, validates each package, and publishes one full DW-SuperApps release containing the package
assets and release evidence.

## Source and delivery separation

- `main` contains source, builders, validators, specs and tests. The release assembler also packages the
  standalone DW control plane under `runtime/`; it is not a documentation-only or Power-only bundle.
- Generated ZIPs are workflow artifacts or release assets.
- Distribution branches are not source of truth.
- Offline consumers use downloaded ZIP artifacts and evidence files only.

## Required lifecycle

```text
SOURCE_LOCK -> BUILD -> VERIFY -> RELEASE_ASSETS -> OFFLINE_INSTALL -> DOCTOR -> REPORT
```

## Evidence required for every release

- `MANIFEST.json`
- `SOURCE_LOCK.json`
- `SHA256SUMS.txt`
- `VALIDATION_REPORT.json`
- `RUNTIME_MANIFEST.json`
- `runtime/bin/dw`, `runtime/scripts/dw_workspace_init.py`, and `runtime/workspace-template.yaml`
- `KIRO_OFFLINE_INSTALL_PROMPT.md`, Kiro installation skill/agent, and Python-session bootstrap
- per-component ZIP artifacts

## Offline acquisition rule

During target installation, do not use Git, GitHub sync, `curl`, `wget`, or remote package acquisition.

## Consumer bootstrap contract

The extracted release is independently executable. It must be able to take a consumer Super Project that is
empty, stale, or broken and perform the following local lifecycle with the release-owned runtime:

```text
VERIFY RELEASE -> REPAIR/CREATE workspace.yaml -> INSTALL CONTROL PLANE
-> INSTALL ROOT PACKAGE STORE -> REGISTER CHILD PROJECT/SYSTEM
-> CREATE TARGET RUNTIME ROOTS -> WRITE BINDINGS -> ACTIVATE HOSTS
-> VALIDATE -> DOCTOR -> REPORT
```

The entrypoint is:

```bash
python offline_release_installer.py setup \
  --release /path/to/extracted-release \
  --workspace /path/to/super-project \
  --workspace-id <id> \
  --workspace-name "<name>" \
  --project-id <id> \
  --project-path projects/<id> \
  --project-source owner/name \
  --system-id <id> \
  --powers all \
  --repair
```

`--project-source` is local metadata only; no remote is contacted. Root-only setup is supported for staging
the shared package store, but its result is `PARTIAL` until a child runtime is registered and doctored. The
package store and target runtime must never overlap. Existing target `.dw/powers` legacy installations are
reported and preserved.

The setup result is `READY` only when package integrity, registration, host routing, workspace validation, and
every selected Power doctor pass. It records `remoteAcquisition: SKIPPED_OFFLINE` and a recoverable backup
under `.dw/history/offline-releases/` when repair replaces managed or broken DW files.

## Ownership

Workspace owns `.dw/powers`, `.dw/history`, `.dw/bindings` and host adapters. Target systems own `.gwc`, `.ua`, `.task-me`, `.bmad` and application source.

## Branch comparison

The legacy `kiro-offline-distribution` branch is retained as delivery evidence only. Its useful intent is Kiro offline package delivery; its binary-only branch shape is replaced by tag/release assets.
