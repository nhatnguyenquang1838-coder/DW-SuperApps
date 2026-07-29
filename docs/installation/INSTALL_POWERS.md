# Install Powers

The supported plug-and-play source is a locally supplied full `DW-SuperApps` release bundle. Each bundle contains a
validated ZIP and matching `.sha256` file for `gwc`, `ua`, `task-me`, and `bmad`, together with release
evidence. Do not perform an online repository or release check. Installation itself is local and must not
acquire packages from Git, GitHub, `curl`, `wget`, or provider branches.

The release contains both:

```text
dw-superapps-full-<version>.zip       # complete offline bundle
assets/<power>-<version>.zip          # individual package assets
assets/<power>-<version>.zip.sha256
offline_release_installer.py         # release-local verifier/installer helper
MANIFEST.json
SOURCE_LOCK.json
SHA256SUMS.txt
VALIDATION_REPORT.json
KIRO_OFFLINE_INSTALL_PROMPT.md  # one Kiro install/register/binding prompt
kiro/skills/dw-power-installation/       # Kiro installation skill + Python session bootstrap
kiro/agents/dw-power-installation.json   # Kiro installation agent
```

Verify an extracted full bundle before installation:

```bash
python /path/to/dw-superapps-full-<version>/offline_release_installer.py verify \
  --release /path/to/dw-superapps-full-<version>
```

The verifier, package ZIPs, checksums, prompt, Kiro skill, Kiro agent, and Python session bootstrap are
inside the release. A receiving Super Project must only provide its local compatible `dw` runtime and
registered project directory; it does not need to pull this repository, Power source repositories, or
remote release assets.

For a DW-SuperApps checkout, place each validated pair in its workspace inbox:

```text
.dw/inbox/powers/gwc/<package>.zip       .dw/inbox/powers/gwc/<package>.zip.sha256
.dw/inbox/powers/ua/<package>.zip        .dw/inbox/powers/ua/<package>.zip.sha256
.dw/inbox/powers/task-me/<package>.zip   .dw/inbox/powers/task-me/<package>.zip.sha256
.dw/inbox/powers/bmad/<package>.zip      .dw/inbox/powers/bmad/<package>.zip.sha256
```

Then install each package into the selected target system:

```bash
dw power install gwc --source package \
  --package .dw/inbox/powers/gwc/<package>.zip \
  --checksum .dw/inbox/powers/gwc/<package>.zip.sha256 \
  --target projects/billing
dw power install ua --source package \
  --package .dw/inbox/powers/ua/<package>.zip \
  --checksum .dw/inbox/powers/ua/<package>.zip.sha256 \
  --target projects/billing
dw power install task-me --source package \
  --package .dw/inbox/powers/task-me/<package>.zip \
  --checksum .dw/inbox/powers/task-me/<package>.zip.sha256 \
  --target projects/billing
dw power install bmad --source package \
  --package .dw/inbox/powers/bmad/<package>.zip \
  --checksum .dw/inbox/powers/bmad/<package>.zip.sha256 \
  --target projects/billing
```

When using the current compatibility layout, the target may still be `systems/<system-id>`.

Complete the lifecycle:

```bash
dw power configure <power-id> \
  --config <config-file> \
  --contract <consumer-contract> \
  --target <project-path>
dw host install all --mode wrapper
dw power doctor <power-id> --target <project-path>
dw doctor all --offline
```

Expected ownership:

```text
Super Project/.dw/powers/<power-id>        package code
Super Project/.dw/bindings/<system>/       binding records
<project>/<runtime-root>/                  runtime and project configuration
Super Project/<host-adapter-root>/         thin adapter
```

The package store is shared by the workspace; runtime data remains target-owned:
`.gwc`, `.ua`, `.task-me`, `.bmad`, `_bmad`, and `_bmad-output` are never copied into the package inbox.
