# Offline Power installation

Use a single full `DW-SuperApps` release when installing into another Super Project. Extract
`dw-superapps-full-<version>.zip`, verify `MANIFEST.json`, `SOURCE_LOCK.json`, `SHA256SUMS.txt`, and
`VALIDATION_REPORT.json`, then copy only the four ZIP/checksum pairs into the receiving workspace inbox.

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
