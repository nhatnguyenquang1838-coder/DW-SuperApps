---
name: dw-power-installation
description: Install, bind, validate, and repair DW Powers from local packages in Kiro, including Windows Git Bash Python compatibility. Use when a Kiro agent must set up a DW Super Project without remote acquisition, register an existing local project, or diagnose package and binding failures.
---

# DW Power Installation

This skill owns the local Kiro workflow for installing DW Power packages into the Super Project package
store and binding them to an existing project/system. It keeps package code in `.dw/powers`, project
runtime in the target project, and never creates a target-local `.dw` Power installation.

## Python session bootstrap

At the beginning of every Kiro installation session, source the bundled bootstrap from the Super Project
root. It detects the first available interpreter in this order: explicit `DW_PYTHON_BIN`/`DW_PYTHON`,
`python3`, `python`, then Windows `py -3`.

```bash
cd "$SUPER_PROJECT"
source .kiro/skills/dw-power-installation/scripts/python-session.sh
dw_kiro_python --version
python3 --version
python --version
py -3 --version
```

The bootstrap exports `DW_PYTHON_BIN`, `DW_PYTHON_ARGS`, `PYTHON`, `PYTHON3`, and `PY`, and defines
working-session functions for `python3`, `python`, and `py`. Use `dw_kiro_python` for deterministic
commands in scripts. Do not assume `python3` exists on Windows.

## Local-only installation workflow

1. Read `workspace.yaml`, the selected system path, and the local release `MANIFEST.json`.
2. Verify the full release with the local script only:

   ```bash
   dw_kiro_python "$SUPER_PROJECT/scripts/offline_release_installer.py" verify --release "$RELEASE_DIR"
   ```

3. Register an existing local project/system once. `--repo` is metadata and `--offline` must be present:

   ```bash
   ./bin/dw project add "$PROJECT_ID" \
     --repo "$PROJECT_SOURCE" \
     --path "$PROJECT_PATH" \
     --role product \
     --role system \
     --system \
     --system-id "$SYSTEM_ID" \
     --enable-powers "$POWERS" \
     --offline
   ```

   The project directory must already exist. Never clone it or run `git submodule add` in this workflow.

4. Install each selected Power from its local ZIP/checksum pair:

   ```bash
   ./bin/dw power install <power-id> \
     --source package \
     --package "$RELEASE_DIR/assets/<package>.zip" \
     --checksum "$RELEASE_DIR/assets/<package>.zip.sha256" \
     --target "$PROJECT_PATH"
   ```

5. Install the Kiro host wrappers only in the Super Project when requested:

   ```bash
   ./bin/dw host install kiro --mode wrapper
   ```

6. Verify each binding at `.dw/bindings/$SYSTEM_ID/<power-id>.json`. It must point to the workspace
   package store and target runtime path.

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
