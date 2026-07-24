# Impact Analysis

## Direct impact

- `DW-SuperApps` gains a distribution contract and build runtime shared by three independently versioned Powers.
- Existing `dw` submodule and host-adapter behavior must remain backward compatible.
- GitHub Actions receives a reusable workflow with write permissions limited to release publishing and `power-dist` updates.

## Transitive impact

- GWC, Task Me, and UA provider tasks depend on the recipe schema and workflow interface remaining stable.
- Task 05 depends on deterministic output and consistent manifest semantics.

## Security and operational impact

- Archive creation can leak secrets or runtime data unless deny rules are enforced after allowlist expansion.
- Symlinks and path traversal can escape repository boundaries.
- Installer writes can overwrite unmanaged consumer files.

## Required controls

- Canonical path normalization.
- Symlink boundary checks.
- Explicit allowlist with a final forbidden-content scan.
- Atomic writes and managed-file markers.
- Checksum verification before extraction.
- Minimal workflow permissions and immutable action references.
