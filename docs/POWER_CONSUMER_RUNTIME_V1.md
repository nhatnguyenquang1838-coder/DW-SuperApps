# DW Power Consumer Runtime v1

The consumer runtime adds package-based Power lifecycle commands while preserving the existing submodule workflow.

## Source modes

| Mode | Behavior |
|---|---|
| `submodule` | Uses the pinned legacy submodule and creates only the consumer runtime-data root. |
| `release` | Downloads a provider release ZIP and checksum using the manifest templates. |
| `power-dist` | Downloads the provider `power-dist` branch archive. |
| `package` | Installs a local validated package directory or ZIP. |
| `auto` | Uses `spec.distribution.defaultMode`; migration defaults remain `submodule`. |

Provider availability is explicit in each Power manifest under `spec.distribution.providerState`. A blocked provider is never silently substituted with another repository.

## Commands

```bash
dw power install task-me --source package --package ./task-me.zip --checksum ./task-me.zip.sha256 --target ./consumer
dw power configure task-me --config ./task-me-config.yaml --contract ./consumer-contract.yaml --target ./consumer
dw power doctor task-me --target ./consumer
dw power history task-me --target ./consumer
dw power rollback task-me --version <version> --target ./consumer
dw power uninstall task-me --target ./consumer
```

Runtime data such as `.task-me`, `.gwc`, and `.ua` is consumer-owned. Uninstall preserves it unless the package runtime receives `--include-runtime --yes`.

## Safety rules

- Release checksums are mandatory when the configured checksum asset is available.
- ZIP extraction rejects absolute paths, parent traversal, and symlinks.
- Package identity must match the requested Power manifest.
- Every file listed in `MANIFEST.json` is size- and SHA-256-verified before installation.
- Unmanaged `.dw/powers/<power>` and history entries are never overwritten or removed.
- Rollback uses only managed history and runs `doctor` before completing.
- Existing submodule commands remain unchanged during migration.

## Current provider state

- **Task Me:** provider recipe and publisher implemented at `711d6314f31a844253bb6719cd28986817768ebc`; release and `power-dist` remain unpublished.
- **GWC:** blocked because repository policy requires formal G0/G1/G2 authority for provider writes.
- **UA:** blocked because `nhatnguyenquang1838-coder/ua-power` does not exist and the connector cannot create or fork repositories.

No provider release, protected-branch merge, deployment, or Gate Control transition is performed by this runtime.
