# PRD: Offline Distribution Revamp

## Problem

The `kiro-offline-distribution` branch is a binary delivery branch. It adds a generated ZIP and checksum, but does not make the release reproducible from source inside a reviewable PR.

## Goal

Implement a release architecture where source remains in `main`, generated packages are created from source at a tag or workflow run, and offline consumers receive only immutable release assets.

## Non-goals

- Do not execute GWC gates or use GWC powers for this task.
- Do not merge generated ZIPs into `main`.
- Do not install runtime data into registered systems.

## Success metrics

- Release builder creates component ZIPs and required evidence.
- Installer verifies every checksum before mutation.
- Existing package components require `--force` to replace.
- Runtime roots are preserved.
- Test covers build, verify, install, force update and rollback.
