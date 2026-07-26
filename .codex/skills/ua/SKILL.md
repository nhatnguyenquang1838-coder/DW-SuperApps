---
name: dw-ua
description: Semantic codebase analysis, architecture discovery, dependency mapping, and project knowledge generation.
---
<!-- generated-by: dw host install -->

# Understand Anything Power

Thin `codex` adapter owned by DW-SuperApps.

- Workspace package store: `.dw/powers`
- Installed package: `.dw/powers/ua`
- Resolved entrypoint: `.dw/powers/ua/understand-anything-plugin/skills/understand`
- Resolution mode: `workspace-store`
- Source fallback: `projects/ua`
- Power manifest: `manifests/powers/ua.yaml`

## Invocation

1. Read `workspace.yaml` and `AGENTS.md` from DW-SuperApps.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Prefer the installed package entrypoint above; use source fallback only when no managed package exists.
5. Keep runtime and project configuration under the target system's `.ua/`.
6. Never create `.dw/powers`, host skill payloads, or distribution history inside the target system.

Generate a complete task prompt with:

`dw power prompt ua --system <system> --task "<task>"`
