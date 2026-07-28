# Architecture: Offline Distribution Revamp

## Current issue

```text
kiro-offline-distribution branch
  -> generated ZIP
  -> checksum
```

This is useful as delivery evidence but weak as source-level implementation.

## Target

```text
main source
  -> release builder
  -> release evidence
  -> component ZIPs
  -> GitHub tag/release assets
  -> offline installer
```

## Package components

- `task-me`
- `bmad`
- `ua`
- `kiro-adapter`
- `bootstrap`

GWC is intentionally not used by this implementation task.

## Safety model

- Generated ZIPs are artifacts, not source.
- Installer rejects unsafe archive paths and symlinks.
- Installer writes only workspace package store.
- Consumer runtime roots are preserved.
