---
name: dw-bmad
description: Route DW SuperApps work through the pinned BMAD Method lifecycle and skills-only distribution.
---

# BMAD Method Power

This is the local routing entrypoint for the release-first BMAD Power.

Canonical DW metadata:

- Power manifest: `manifests/powers/bmad.yaml`
- Source lock: `plugins/bmad-method/SOURCE.lock.json`
- Architecture graph: `plugins/bmad-method/knowledge/knowledge-graph.json`
- Distribution recipe: `plugins/bmad-method/distribution/power-package.yaml`

## Invocation

1. Read `workspace.yaml` and `AGENTS.md`.
2. Resolve the target system and confirm `bmad` is enabled.
3. Use the package lifecycle to install the pinned BMAD release into the consumer.
4. Run the package `doctor` command.
5. Run `distribution/bin/bootstrap-bmad` for the selected host.
6. Keep BMAD output under the consumer-owned `_bmad`, `_bmad-output`, `docs`, and `.bmad` paths allowed by the consumer contract.

Generate a host-neutral prompt with:

```bash
dw power prompt bmad --system <system> --task "<task>"
```

Install after a release is published:

```bash
dw power install bmad --source release --version <version> --target <consumer>
```

Do not modify the BMAD upstream repository through this wrapper.
