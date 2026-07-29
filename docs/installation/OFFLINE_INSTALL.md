# Offline full-project installation

Use the extracted `dw-superapps-full-<version>` directory as the only input. The bundle contains the control
plane, workspace template, Kiro prompt/skill/agent, Python session bootstrap, Power ZIP/checksum pairs, and
release evidence. A receiving project does not need to pull DW-SuperApps, Power sources, or GitHub.

Verify locally:

```bash
source /path/to/dw-superapps-full-<version>/kiro/skills/dw-power-installation/scripts/python-session.sh
dw_kiro_python /path/to/dw-superapps-full-<version>/offline_release_installer.py verify \
  --release /path/to/dw-superapps-full-<version>
```

Bootstrap or repair the Super Project and register a child project in one operation:

```bash
dw_kiro_python /path/to/dw-superapps-full-<version>/offline_release_installer.py setup \
  --release /path/to/dw-superapps-full-<version> \
  --workspace /path/to/super-project \
  --workspace-id <workspace-id> \
  --workspace-name "<workspace-name>" \
  --project-id <project-id> \
  --project-path projects/<project-id> \
  --project-source owner/name \
  --system-id <system-id> \
  --powers all \
  --repair
```

The target may be empty, stale, or broken. `--repair` backs up replaced DW-managed files under
`.dw/history/offline-releases/` and preserves unrelated files. `--project-source` is local owner/name
metadata; no remote is contacted. For a new child with no local Git remote, it is required.

Root-only mode is also supported by omitting the child arguments. It installs `.dw/powers` and the control
plane but reports `PARTIAL` until a child runtime is registered and doctored.

The final ownership split is:

```text
<super-project>/.dw/powers/<power-id>/       shared package code
<super-project>/.dw/bindings/<system>/       bindings
<super-project>/<project>/.gwc/              target runtime/configuration
<super-project>/<project>/.ua/
<super-project>/<project>/.task-me/
<super-project>/<project>/.bmad/
```

Do not put package payloads, host skills, or `<power-id>` under `<project>/.dw`. Existing legacy target
installations are reported and preserved. Use the JSON result, `bin/dw validate`, host status, and Power
doctors as the completion evidence. Report `remoteAcquisition: SKIPPED_OFFLINE`.
