# Offline Power installation

Use a single full `DW-SuperApps` release when installing into another Super Project. Extract
`dw-superapps-full-<version>.zip`, verify `MANIFEST.json`, `SOURCE_LOCK.json`, `SHA256SUMS.txt`, and
`VALIDATION_REPORT.json`, then copy only the four ZIP/checksum pairs into the receiving workspace inbox.

The release also contains `KIRO_OFFLINE_INSTALL_PROMPT.md`. This is the single Kiro prompt for offline
installation and project binding; the release does not need copied Kiro Power adapters.

Register an existing local project and its system metadata without creating a submodule:

```bash
./bin/dw project add <project-id> \
  --repo <owner/name> \
  --path <existing-relative-project-path> \
  --role product \
  --role system \
  --system \
  --system-id <system-id> \
  --enable-powers gwc,ua,task-me,bmad \
  --offline
```

In this mode `--repo` is metadata only. The path must already exist locally, and no GitHub, Git,
submodule, or remote checksum check is performed.

The full release is authoritative for the package set; do not mix a BMAD asset from the retired standalone
BMAD release with assets from a different full-release version.

Place each validated ZIP and checksum in the Super Project inbox:

```text
.dw/inbox/powers/<power-id>/<package>.zip
.dw/inbox/powers/<power-id>/<package>.zip.sha256
```

Install without remote acquisition:

```bash
dw power install <power-id> \
  --source package \
  --package .dw/inbox/powers/<power-id>/<package>.zip \
  --checksum .dw/inbox/powers/<power-id>/<package>.zip.sha256 \
  --target <project-path>
```

Then configure, activate hosts, invoke once, and run doctor. Offline mode must not clone source projects, download releases, or initialize Power submodules for package acquisition.

The expected final split is:

```text
<super-project>/.dw/powers/{gwc,ua,task-me,bmad}/
<super-project>/.dw/bindings/<system>/{gwc,ua,task-me,bmad}.json
<target-system>/.gwc
<target-system>/.ua
<target-system>/.task-me
<target-system>/.bmad
```
