---
name: dw-gwc
description: Governance, delivery control, approval boundaries, validation, and repository lifecycle workflows.
---
<!-- generated-by: dw host install -->

# GWC Power

Thin `codex` adapter owned by DW-SuperApps.

- Workspace package store: `.dw/powers`
- Installed package: `.dw/powers/gwc`
- Resolved entrypoint: `projects/gwc/skills/gwc-g1`
- Resolution mode: `source-submodule-fallback`
- Source fallback: `projects/gwc`
- Power manifest: `manifests/powers/gwc.yaml`

## Invocation

1. Read `workspace.yaml` and `AGENTS.md` from DW-SuperApps.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Prefer the installed package entrypoint above; use source fallback only when no managed package exists.
5. Keep runtime and project configuration under the target system's `.gwc/`.
6. Never create `.dw/powers`, host skill payloads, or distribution history inside the target system.

Generate a complete task prompt with:

`dw power prompt gwc --system <system> --task "<task>"`
