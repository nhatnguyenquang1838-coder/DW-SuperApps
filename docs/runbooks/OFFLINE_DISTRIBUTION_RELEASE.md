# Offline Distribution Release Runbook

## Purpose

Replace branch-based offline distribution with source-built, tag/download-only release artifacts.

The aggregate release workflow is `.github/workflows/publish-full-distribution-release.yml`. It runs on
`dw-superapps-v*` tags or manual dispatch, builds `gwc`, `ua`, `task-me`, and `bmad` from the checked-out
source pins, validates each package, and publishes one full DW-SuperApps release containing the package
assets and release evidence.

## Source and delivery separation

- `main` contains source, builders, validators, specs and tests.
- Generated ZIPs are workflow artifacts or release assets.
- Distribution branches are not source of truth.
- Offline consumers use downloaded ZIP artifacts and evidence files only.

## Required lifecycle

```text
SOURCE_LOCK -> BUILD -> VERIFY -> RELEASE_ASSETS -> OFFLINE_INSTALL -> DOCTOR -> REPORT
```

## Evidence required for every release

- `MANIFEST.json`
- `SOURCE_LOCK.json`
- `SHA256SUMS.txt`
- `VALIDATION_REPORT.json`
- per-component ZIP artifacts

## Offline acquisition rule

During target installation, do not use Git, GitHub sync, `curl`, `wget`, or remote package acquisition.

## Ownership

Workspace owns `.dw/powers`, `.dw/history`, `.dw/bindings` and host adapters. Target systems own `.gwc`, `.ua`, `.task-me`, `.bmad` and application source.

## Branch comparison

The legacy `kiro-offline-distribution` branch is retained as delivery evidence only. Its useful intent is Kiro offline package delivery; its binary-only branch shape is replaced by tag/release assets.
