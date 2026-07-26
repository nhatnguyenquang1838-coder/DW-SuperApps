---
name: dw-task-me
description: Impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
---
<!-- generated-by: dw host install -->

# Task Me Power

Thin `kiro` adapter owned by DW-SuperApps.

- Workspace package store: `.dw/powers`
- Installed package: `.dw/powers/task-me`
- Resolved entrypoint: `.dw/powers/task-me/.kiro/skills/implementation-task-architect`
- Resolution mode: `workspace-store`
- Source fallback: `projects/task-me`
- Power manifest: `manifests/powers/task-me.yaml`

## Invocation

1. Read `workspace.yaml` and `AGENTS.md` from DW-SuperApps.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Prefer the installed package entrypoint above; use source fallback only when no managed package exists.
5. Keep runtime and project configuration under the target system's `.task-me/`.
6. Never create `.dw/powers`, host skill payloads, or distribution history inside the target system.

Generate a complete task prompt with:

`dw power prompt task-me --system <system> --task "<task>"`
