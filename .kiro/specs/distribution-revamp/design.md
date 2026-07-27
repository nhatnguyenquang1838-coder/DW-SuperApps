# Design

## Overview

The revamp converts offline distribution from a branch-carried binary delivery into a source-built release pipeline.

```text
source branch
  -> release_builder.py
  -> release root
  -> component ZIPs + evidence
  -> GitHub release assets / workflow artifacts
  -> offline installer
```

## Components

### Release builder

`scripts/release_builder.py` creates component ZIPs and release evidence from a source tree. It rejects missing component roots and excludes development-only directories such as `.git`, `.github`, `node_modules`, and bytecode caches.

### Offline installer

`scripts/offline_release_installer.py` verifies release evidence, rejects unsafe ZIP entries and installs component packages into workspace `.dw/powers`.

### Evidence schema

`schemas/distribution-release.schema.json` defines the release manifest contract.

### Workflow

`.github/workflows/offline-distribution-release.yml` builds and tests artifacts without committing generated ZIPs back to the source branch.

## Ownership boundary

- Distribution packages: workspace `.dw/powers`
- Package history: workspace `.dw/history/offline-releases`
- Bindings: workspace `.dw/bindings/offline-releases`
- Consumer runtime: `.gwc`, `.ua`, `.task-me`, `.bmad`
