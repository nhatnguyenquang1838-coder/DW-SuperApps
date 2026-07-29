# Kiro offline install and project binding prompt

You are Kiro operating an offline DW-SuperApps installation. Use only the local full-release directory
and the local Super Project checkout supplied by the user.

## Hard offline boundary

- Do not use GitHub, `git clone`, `git fetch`, `git pull`, `git submodule add`, `gh`, `curl`, `wget`, or
  any remote package/provider source.
- Do not check a remote repository, release, branch, tag, or online checksum.
- Treat the local `MANIFEST.json`, `SOURCE_LOCK.json`, `SHA256SUMS.txt`, `VALIDATION_REPORT.json`, ZIPs,
  and matching `.sha256` files as the only distribution evidence.
- Stop and report `BLOCKED_OFFLINE` if a required local asset or checksum is missing.

## Inputs required from the user

Collect these values before changing anything:

```text
RELEASE_DIR       extracted full release directory
SUPER_PROJECT     local DW-SuperApps checkout
PROJECT_ID        lowercase local project/system identifier
PROJECT_PATH      existing path relative to SUPER_PROJECT
PROJECT_SOURCE    owner/name metadata for the local project; no remote check
SYSTEM_ID         system identifier used by bindings
POWERS            comma-separated subset of gwc,ua,task-me,bmad
```

## Procedure

1. Verify the extracted release locally:

   ```bash
   python "$SUPER_PROJECT/scripts/offline_release_installer.py" verify --release "$RELEASE_DIR"
   ```

2. Confirm `PROJECT_PATH` already exists as a local directory. Do not create or clone project source.

3. Register the local project and system without network or submodule mutation:

   ```bash
   cd "$SUPER_PROJECT"
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

4. For each selected Power, install only its local release asset:

   ```bash
   ./bin/dw power install <power-id> \
     --source package \
     --package "$RELEASE_DIR/assets/<package>.zip" \
     --checksum "$RELEASE_DIR/assets/<package>.zip.sha256" \
     --target "$PROJECT_PATH"
   ```

   Resolve `<package>.zip` and its checksum from the local release `MANIFEST.json`; never guess a version.

5. Confirm the resulting binding exists at:

   ```text
   $SUPER_PROJECT/.dw/bindings/$SYSTEM_ID/<power-id>.json
   ```

   The binding must contain the registered system target, installed package path, package version,
   manifest digest, and runtime path. Do not modify runtime data outside the declared project roots.

6. Report the local paths and binding files. Do not claim online provenance or remote synchronization.
