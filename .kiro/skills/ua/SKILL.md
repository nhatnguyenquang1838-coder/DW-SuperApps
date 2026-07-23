---
name: dw-ua
description: Semantic codebase analysis, architecture discovery, dependency mapping, and project knowledge generation.
---
<!-- generated-by: dw host install -->

# Understand Anything Power

This is a thin `kiro` adapter. Canonical behavior remains in:

- Power source: `../../../powers/ua`
- Power manifest: `../../../manifests/powers/ua.yaml`
- Preferred entrypoint: `../../../powers/ua/understand-anything-plugin/skills/understand`

## Invocation

1. Read `../../../workspace.yaml` and `../../../AGENTS.md`.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Read the canonical Power entrypoint above.
5. Keep generated data under the target system's `.ua/`.
6. Never store project runtime data in the Power submodule.

Use `dw power prompt ua --system <system> --task "<task>"` to generate a host-neutral invocation prompt.
