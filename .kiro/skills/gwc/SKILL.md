---
name: dw-gwc
description: Governance, delivery control, approval boundaries, validation, and repository lifecycle workflows.
---
<!-- generated-by: dw host install -->

# GWC Power

This is a thin `kiro` adapter. Canonical behavior remains in:

- Power source: `../../../powers/gwc`
- Power manifest: `../../../manifests/powers/gwc.yaml`
- Preferred entrypoint: `../../../powers/gwc/skills/gwc-g1`

## Invocation

1. Read `../../../workspace.yaml` and `../../../AGENTS.md`.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Read the canonical Power entrypoint above.
5. Keep generated data under the target system's `.gwc/`.
6. Never store project runtime data in the Power submodule.

Use `dw power prompt gwc --system <system> --task "<task>"` to generate a host-neutral invocation prompt.
