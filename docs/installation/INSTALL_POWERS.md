# Install Powers from a full offline release

The supported plug-and-play input is the extracted `dw-superapps-full-<version>` release directory. It is
self-contained: it carries the DW control plane, workspace template, Kiro prompt/skill/agent, Python-session
bootstrap, Power ZIPs, and checksums. The receiving project does not need a DW-SuperApps checkout or Power
source repositories.

The release supports a target that is:

- empty and not yet initialized;
- stale or partially initialized; or
- broken, with a recoverable DW runtime, registry, host adapter, or package store.

All acquisition is offline. Do not run GitHub/release checks, `git fetch`, `curl`, `wget`, remote `power-dist`,
or submodule initialization to acquire Powers.

## Verify the release

Run the verifier shipped inside the release. On Kiro/Git Bash, first source the shipped Python session helper
so `python3`, `python`, and `py` all resolve to the same validated Python 3 interpreter:

```bash
source /path/to/dw-superapps-full-<version>/kiro/skills/dw-power-installation/scripts/python-session.sh
dw_kiro_python /path/to/dw-superapps-full-<version>/offline_release_installer.py verify \
  --release /path/to/dw-superapps-full-<version>
```

On Windows Git Bash, `py -3` is used when `python3`/`python` are unavailable. If PyYAML is missing, install
from the release-local `runtime/requirements-dev.txt` using an already available offline wheel/cache; do not
download dependencies during setup.

## Full setup: root package store plus a child project

`--workspace` is the Super Project root. The shared package store is placed under
`<workspace>/.dw/powers`. A child project is the runtime owner for `.gwc`, `.ua`, `.task-me`, or `.bmad` and
receives bindings; it must not receive Power package payloads or host skill copies.

```bash
RELEASE_DIR=/path/to/dw-superapps-full-<version>
SUPER_PROJECT=/path/to/my-super-project

source "$RELEASE_DIR/kiro/skills/dw-power-installation/scripts/python-session.sh"
dw_kiro_python "$RELEASE_DIR/offline_release_installer.py" setup \
  --release "$RELEASE_DIR" \
  --workspace "$SUPER_PROJECT" \
  --workspace-id my-super-project \
  --workspace-name "My Super Project" \
  --project-id app \
  --project-path projects/app \
  --project-source owner/app \
  --system-id app \
  --powers all \
  --repair
```

`--project-source owner/app` is local repository metadata only; it is not contacted. Omit it only when the
existing child has a local Git `remote.origin.url` that can be read without contacting the remote. For an empty
child with no local remote, the value is required.

The command creates or repairs `workspace.yaml`, initializes the local control-plane Git repository when
needed, installs the package store, registers the project/system, creates target runtime roots, writes bindings,
generates host adapters, and runs workspace validation plus Power doctors. `--repair` backs up replaced files
under `<workspace>/.dw/history/offline-releases/<timestamp>/` and preserves unrelated files.

Expected ownership:

```text
<workspace>/.dw/powers/<power-id>/       shared package code
<workspace>/.dw/bindings/<system>/       package-to-target bindings
<workspace>/<project>/.gwc/              target runtime/configuration
<workspace>/<project>/.ua/
<workspace>/<project>/.task-me/
<workspace>/<project>/.bmad/
<workspace>/<host-adapter-root>/         thin host adapters
```

Do not create `<project>/.dw/powers` or copy Kiro skill payloads into the child project. Existing legacy paths
there are reported and preserved.

## Root-only package installation

If the child project is not known yet, omit all child arguments:

```bash
dw_kiro_python "$RELEASE_DIR/offline_release_installer.py" setup \
  --release "$RELEASE_DIR" \
  --workspace "$SUPER_PROJECT" \
  --workspace-id my-super-project \
  --workspace-name "My Super Project" \
  --powers all \
  --repair
```

This installs the shared root package store and control plane, but reports `PARTIAL` because there is no
project runtime to bind or doctor. Run the full setup again after supplying `--project-id`, `--project-path`,
and local `--project-source` metadata.

## Result and recovery

The JSON result records exact release/workspace paths, selected Powers, package actions, bindings, host status,
validation, doctor results, backup history, and `remoteAcquisition: SKIPPED_OFFLINE`.

- `READY`: package integrity, registration, host routing, validation, and every selected Power doctor pass;
- `PARTIAL`: root package/control-plane setup succeeded but a child runtime or required activation is incomplete;
- `BLOCKED`: safe repair, Python dependency, project identity, or local metadata is unavailable;
- `FAILED`: an executed operation returned a real failure.

Before using the project, inspect the result and verify:

```bash
test -f "$SUPER_PROJECT/workspace.yaml"
test -d "$SUPER_PROJECT/.dw/powers"
test -f "$SUPER_PROJECT/.dw/bindings/app/gwc.json"
"$SUPER_PROJECT/bin/dw" host status all
"$SUPER_PROJECT/bin/dw" validate
```

## Understand the four Powers

After setup, the release includes an offline help command for each Power. It
explains what it is for, when to use it, how to invoke it, why it exists, what
the user gets, and its authority boundaries:

```bash
"$SUPER_PROJECT/bin/dw" power help gwc
"$SUPER_PROJECT/bin/dw" power help ua
"$SUPER_PROJECT/bin/dw" power help task-me
"$SUPER_PROJECT/bin/dw" power help bmad
```

For an ergonomic alias, use:

```bash
"$SUPER_PROJECT/bin/dw" skill gwc --help
```

The help command is read-only and offline. It is not a Power activation
command and does not generate a task prompt. Use the selected native host
alias, such as `/dw-gwc`, `/dw-ua`, `/dw-task-me`, or `/dw-bmad`, to perform
work in the current agent session.

Use only the release-local `offline_release_installer.py` and runtime after extraction. Do not fall back to
scripts from a different DW-SuperApps checkout because that can reintroduce version drift.
