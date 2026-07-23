---
name: dw-task-me
description: Impact analysis, implementation planning, task decomposition, coding guidance, and validation planning.
---
<!-- generated-by: dw host install -->

# Task Me Power

This is a thin `codex` adapter. Canonical behavior remains in:

- Power source: `../../../powers/task-me`
- Power manifest: `../../../manifests/powers/task-me.yaml`
- Preferred entrypoint: `../../../powers/task-me/.kiro/skills/implementation-task-architect`

## Invocation

1. Read `../../../workspace.yaml` and `../../../AGENTS.md`.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Read the canonical Power entrypoint above.
5. Keep generated data under the target system's `.task-me/`.
6. Never store project runtime data in the Power submodule.

Use `dw power prompt task-me --system <system> --task "<task>"` to generate a host-neutral invocation prompt.
