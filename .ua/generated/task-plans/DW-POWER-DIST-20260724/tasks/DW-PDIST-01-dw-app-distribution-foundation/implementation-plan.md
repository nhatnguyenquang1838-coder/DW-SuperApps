# Implementation Plan

1. Define schema identifiers and compatibility rules for distribution recipe, package manifest, and consumer binding.
2. Add positive and negative fixtures before implementing the builder.
3. Implement recipe loading, schema validation, path normalization, include expansion, exclude filtering, and forbidden-content validation.
4. Build a clean staging tree and generate `POWER.yaml`, `SOURCE.json`, `MANIFEST.json`, and `VERSION`.
5. Generate a normalized deterministic ZIP and SHA-256 checksum.
6. Add portable runtime templates with managed-file markers and atomic installation behavior.
7. Add `doctor` validation for manifest, checksum, entrypoints, configuration, contract, and runtime-root boundaries.
8. Add the reusable workflow with explicit inputs, minimal permissions, concurrency protection, smoke installation, release publishing, and `power-dist` synchronization.
9. Add Linux, macOS, and Windows test coverage where the runtime differs.
10. Run the full existing DW test suite to confirm legacy submodule and host-adapter behavior remains intact.
