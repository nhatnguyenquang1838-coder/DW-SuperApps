---
name: dw-power-installation
description: Install, bind, validate, and repair DW Powers from local packages in Kiro, including Windows Git Bash Python compatibility. Use when a Kiro agent must set up a DW Super Project without remote acquisition, register an existing local project, or diagnose package and binding failures.
---

# DW Power Installation

This skill owns the local Kiro workflow for bootstrapping an empty, stale, or broken Super Project from a
full offline release. It keeps package code in `.dw/powers`, project runtime in an optional child target,
and never creates a target-local `.dw` Power installation. Root-only mode installs the shared package store
but remains `PARTIAL` until a child runtime is registered and doctored.

## Python session bootstrap

At the beginning of every Kiro installation session, source the bundled bootstrap from the Super Project
root. It detects the first available interpreter in this order: explicit `DW_PYTHON_BIN`/`DW_PYTHON`,
`python3`, `python`, then Windows `py -3`.

```bash
cd "$SUPER_PROJECT"
source .kiro/skills/dw-power-installation/scripts/python-session.sh
dw_python_init
dw_kiro_python --version
```

`dw_python_init` is mandatory and fail-fast: it executes `--version` through the resolved launcher and
rejects a broken shim or non-Python-3 executable. The bootstrap exports `DW_PYTHON_BIN`,
`DW_PYTHON_ARGS`, `PYTHON`, `PYTHON3`, and `PY`, and defines working-session functions for `python3`,
`python`, and `py`. Use `dw_kiro_python` for deterministic commands in scripts. Do not assume `python3`
exists on Windows.

## Local-only full setup workflow

1. Read the local release `MANIFEST.json` and resolve whether the target is empty, stale, or broken.
2. Verify the full release with the release-owned script only:

   ```bash
   dw_kiro_python "$RELEASE_DIR/offline_release_installer.py" verify --release "$RELEASE_DIR"
   ```

   The verifier is part of the extracted release. Do not replace it with a copy from a repository
   checkout.

3. Run the release-owned setup command. It bootstraps the DW control plane, creates or repairs
   `workspace.yaml`, installs the root package store, optionally registers a child project/system, binds
   runtime roots, generates host adapters, and runs local validation/doctor:

   ```bash
   dw_kiro_python "$RELEASE_DIR/offline_release_installer.py" setup \
     --release "$RELEASE_DIR" \
     --workspace "$SUPER_PROJECT" \
     --workspace-id "$WORKSPACE_ID" \
     --workspace-name "$WORKSPACE_NAME" \
     --project-id "$PROJECT_ID" \
     --project-path "$PROJECT_PATH" \
     --project-source "$PROJECT_SOURCE" \
     --system-id "$SYSTEM_ID" \
     --powers "$POWERS" \
     --repair
   ```

   `PROJECT_SOURCE` is local owner/name metadata only. It may be detected from an existing local Git
   remote, but no remote is contacted. `--repair` backs up replaced DW runtime/package files under
   `.dw/history/offline-releases/` and preserves unrelated user files.

4. For root-only package installation, omit the child project arguments. This installs packages into the
   Super Project `.dw/powers` store but must report `PARTIAL` because no runtime target can be doctored.

5. Confirm each binding at `.dw/bindings/$SYSTEM_ID/<power-id>.json`, host status, workspace validation,
   Power doctor, and the reported backup path. Do not claim `READY` when any required phase is incomplete.

## Safety boundaries

- Do not call GitHub, `gh`, `git clone`, `git fetch`, `git pull`, `curl`, `wget`, or remote package sources.
- Do not write package payloads, host adapters, or `.dw` directories inside the target project.
- Preserve target runtime data unless the user explicitly requests the destructive cleanup command with confirmation.
- Reject missing local assets, mismatched checksums, path traversal, archive symlinks, store/runtime overlap,
  unmanaged overwrite, or package identity mismatch.
- Do not invent repository metadata, checksums, credentials, approvals, or binding evidence.

## Report

Return the selected project/system, interpreter command, source mode, exact package paths/checksums,
binding files, changed paths, and one status: `READY`, `PARTIAL`, `BLOCKED`, or `FAILED`. Do not call
the setup `READY` until package integrity, binding, host routing, and local doctor checks pass.
