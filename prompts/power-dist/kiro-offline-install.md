# Kiro offline full bootstrap and Power installation prompt

You are Kiro operating an offline DW-SuperApps installation. Use only the local full-release directory
and the local Super Project checkout supplied by the user.

## Hard offline boundary

- Do not use GitHub, `git clone`, `git fetch`, `git pull`, `git submodule add`, `gh`, `curl`, `wget`, or
  any remote package/provider source.
- Do not check a remote repository, release, branch, tag, or online checksum.
- Treat the local `MANIFEST.json`, `SOURCE_LOCK.json`, `SHA256SUMS.txt`, `VALIDATION_REPORT.json`, ZIPs,
  and matching `.sha256` files as the only distribution evidence.
- Stop and report `BLOCKED_OFFLINE` if a required local asset or checksum is missing.

## Target model

The target may be:

- empty: no DW runtime or `workspace.yaml` yet;
- stale: an older DW runtime or registry exists; or
- broken: partial `.dw`, host adapters, or registry files exist.

The release repairs only DW-managed control-plane files and stores replaced files in the workspace
history. It never overwrites an unrelated project file silently.

"Root install" means the shared Power package store under `SUPER_PROJECT/.dw/powers`. A runtime binding
must target a child project so the package store and system runtime cannot overlap. A root-only install is
reported `PARTIAL` until a child system is registered and doctored.

## Inputs required from the user

Collect these values before changing anything:

```text
RELEASE_DIR       extracted full release directory
SUPER_PROJECT     local target workspace; may be empty, stale, or broken
WORKSPACE_ID      lowercase workspace identifier
WORKSPACE_NAME    display name for a new workspace registry
PROJECT_ID        optional lowercase child project/system identifier
PROJECT_PATH      optional child path relative to SUPER_PROJECT
PROJECT_SOURCE    optional owner/name metadata; local metadata only, no remote check
SYSTEM_ID         optional system identifier; defaults to PROJECT_ID
POWERS            comma-separated subset of gwc,ua,task-me,bmad, or all
```

## Procedure

1. Start and validate the Windows Bash-compatible Python session before any verifier or setup command:
   installation command. Prefer the resolver shipped in the local release so bootstrap does not depend
   on the target checkout already containing `scripts/`:

   ```bash
   cd "$SUPER_PROJECT"
   if [ -f "$RELEASE_DIR/kiro/skills/dw-power-installation/scripts/python-session.sh" ]; then
     source "$RELEASE_DIR/kiro/skills/dw-power-installation/scripts/python-session.sh"
   elif [ -f scripts/kiro-python-session.sh ]; then
     source scripts/kiro-python-session.sh
   else
     source scripts/python-resolver.sh
   fi
   dw_python_init
   dw_kiro_python --version
   ```

   `dw_python_init` is mandatory and fail-fast: it resolves the launcher, executes `--version`, and
   rejects a broken shim or a non-Python-3 executable. The equivalent non-interactive preflight is
   `./bin/dw python init`; it validates the interpreter but cannot export functions into the parent
   shell, so the current Kiro Bash session must still source the bootstrap above.

2. Verify the extracted full release locally:

   ```bash
   release_verifier="$RELEASE_DIR/offline_release_installer.py"
   test -f "$release_verifier"
   dw_kiro_python "$release_verifier" verify --release "$RELEASE_DIR"
   ```

   The verifier is shipped inside the release. Do not replace it with a copy from a repository checkout.

3. Run the release-owned full setup. This copies the control plane into the target, creates or repairs
   `workspace.yaml`, installs Power packages in the root store, registers an optional child project, binds
   runtime roots, installs host adapters, and runs validation/doctor.

   ```bash
   setup_args=(
     setup
     --release "$RELEASE_DIR"
     --workspace "$SUPER_PROJECT"
     --workspace-id "$WORKSPACE_ID"
     --workspace-name "$WORKSPACE_NAME"
     --powers "$POWERS"
     --repair
   )
   if [ -n "${PROJECT_ID:-}" ]; then
     setup_args+=(
       --project-id "$PROJECT_ID"
       --project-path "$PROJECT_PATH"
       --system-id "${SYSTEM_ID:-$PROJECT_ID}"
     )
     if [ -n "${PROJECT_SOURCE:-}" ]; then
       setup_args+=(--project-source "$PROJECT_SOURCE")
     fi
   fi
   dw_kiro_python "$RELEASE_DIR/offline_release_installer.py" "${setup_args[@]}"
   ```

   `--repair` is intentional for stale/broken targets. Replaced DW files and previous package stores are
   backed up under `SUPER_PROJECT/.dw/history/offline-releases/`; unrelated `AGENTS.md` and dependency
   files are preserved rather than overwritten. If no child project is supplied, package installation is
   root-only and the result must remain `PARTIAL`.

4. Read the JSON setup result and confirm, for a child installation:

   ```text
   SUPER_PROJECT/.dw/powers/<power-id>/
   SUPER_PROJECT/.dw/bindings/<SYSTEM_ID>/<power-id>.json
   PROJECT_PATH/.gwc/        PROJECT_PATH/.ua/
   PROJECT_PATH/.task-me/    PROJECT_PATH/.bmad/
   ```

   The result is `READY` only when package integrity, registration, host activation, workspace validation,
   and every selected Power doctor pass. Report `PARTIAL`, `BLOCKED`, or `FAILED` with the exact phase
   and backup path otherwise. Always report `remoteAcquisition: SKIPPED_OFFLINE`.
