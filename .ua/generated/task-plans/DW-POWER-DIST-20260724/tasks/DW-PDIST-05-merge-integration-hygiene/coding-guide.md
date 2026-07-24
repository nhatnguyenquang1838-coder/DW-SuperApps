# Coding Guide

## Integration evidence

Create a machine-readable compatibility record keyed by Power ID. Record source repository/SHA, distribution repository/SHA, contract version, workflow SHA, release version, asset hash, `power-dist` SHA, runtime root, and supported hosts.

## DW manifest evolution

Add distribution fields without deleting current `spec.path`, `spec.source`, entrypoint, capability, permission, or runtime data declarations. The CLI should resolve a configured source mode rather than hard-code release behavior.

## Atomic installation and rollback

Download to a cache, verify checksum and manifest, extract to a temporary directory, run package `doctor`, then atomically replace the managed Power installation. Keep the prior verified version until post-install doctor succeeds. Never delete consumer runtime data during rollback.

## Hygiene

Scan for `.env*`, secrets, caches, staging directories, generated task plans outside this approved spec branch, populated `.gwc/.ua/.task-me` directories, dashboards, UI bundles, duplicate adapters, stale examples, temporary archives, and checksum drift.
