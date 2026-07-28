# DW SUPER Offline ZIP Onboarding Prompt

```text
Onboard DW SUPER from local Power ZIPs for the selected target system.

GitHub and outbound Power acquisition are unavailable. DW-SuperApps is the distribution and host-control workspace. The selected system owns runtime and project configuration only.

Search only in:
DW-SuperApps/.dw/inbox/powers/<power-id>/

Require one valid ZIP and matching .zip.sha256 sidecar unless an exact path was supplied. Verify archive checksum, package identity, MANIFEST.json, all declared sizes/hashes, entrypoints, and runtimeDataRoot.

Install with:
./bin/dw power install <power-id> \
  --source package \
  --package .dw/inbox/powers/<power-id>/<package>.zip \
  --checksum .dw/inbox/powers/<power-id>/<package>.zip.sha256 \
  --target systems/<system-id>

Requirements:
- Packages, inbox, cache, history, bindings, router, and host adapters remain in DW-SuperApps.
- Runtime and configuration remain in the selected system's declared roots.
- Do not create `<system>/.dw/powers` or host skill payloads.
- Detect LEGACY_TARGET_INSTALL and leave it untouched.
- Generate adapters with `./bin/dw host install all --mode wrapper`.
- Resolve the workspace installed package before source fallback.
- Do not run remote Git, release, curl, wget, or power-dist acquisition commands.
- Preserve inbox ZIP/checksum and existing runtime data.
- Run local package, binding, runtime, configuration, host, dedupe, workspace, and invocation checks.
- Return explicit confirmation that no remote acquisition ran.
```
