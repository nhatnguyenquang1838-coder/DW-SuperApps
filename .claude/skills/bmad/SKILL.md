---
name: dw-bmad
description: Structured software-delivery lifecycle covering analysis, planning, architecture, implementation, and review.
---
<!-- generated-by: dw host install -->

# BMAD Method Power

Thin `claude` adapter owned by DW-SuperApps.

- Workspace package store: `.dw/powers`
- Installed package: `.dw/powers/bmad`
- Resolved entrypoint: `projects/bmad/src/core-skills/bmad-help`
- Resolution mode: `source-submodule-fallback`
- Source fallback: `projects/bmad`
- Power manifest: `manifests/powers/bmad.yaml`

## Invocation

1. Read `workspace.yaml` and `AGENTS.md` from DW-SuperApps.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Prefer the installed package entrypoint above; use source fallback only when no managed package exists.
5. Keep runtime and project configuration under the target system's `.bmad/`.
6. Never create `.dw/powers`, host skill payloads, or distribution history inside the target system.

Generate a complete task prompt with:

`dw power prompt bmad --system <system> --task "<task>"`
