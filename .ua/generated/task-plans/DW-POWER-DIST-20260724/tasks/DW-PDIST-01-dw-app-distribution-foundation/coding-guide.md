# Coding Guide

## Builder

Implement the builder as a standalone Python module under `scripts/power_dist.py`. Keep pure functions for recipe validation, staging, manifest generation, archive generation, and checksum generation so tests can isolate each stage.

Use `pathlib.Path.resolve()` and verify every resolved source and destination remains under the expected root. Reject absolute patterns, `..`, external symlink targets, duplicate destinations, case-collision risks, and output paths inside the source tree.

Sort all manifest entries and ZIP members by POSIX path. Normalize archive timestamps, permissions, and line-ending treatment only where the contract explicitly requires it.

## Runtime templates

Use a generated marker for every managed adapter/config file. Refuse replacement when the marker is absent. Use temporary files followed by atomic rename. Preserve `.gwc`, `.ua`, and `.task-me` data during uninstall unless destructive cleanup is explicitly requested.

## Workflow

Make the reusable workflow callable with `workflow_call`. Validate before granting publish steps access to write tokens. Pin third-party actions by immutable commit SHA. Ensure the release ZIP and `power-dist` are built from the same staged directory.
