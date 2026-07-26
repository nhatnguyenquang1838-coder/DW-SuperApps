# Offline Power installation

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
