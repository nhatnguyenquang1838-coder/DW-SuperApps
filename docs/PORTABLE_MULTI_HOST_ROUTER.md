# Portable Multi-Host Router Contract

## Goal

Allow the same DW-SuperApps workspace to be opened in Codex, Kiro, Kilo Code, GitHub Copilot, Claude Code, Cline, or a configured custom host without reinstalling Powers or changing a global active-host setting.

## Core model

```text
DW-SuperApps workspace
  -> shared managed Power store: .dw/powers/
  -> one canonical DW router when implemented
  -> thin native adapters in DW-SuperApps
  -> selected project runtime/configuration root
```

Canonical distribution locations:

```text
DW-SuperApps/.dw/powers/<power-id>/
DW-SuperApps/.dw/router/SKILL.md             # when implemented
DW-SuperApps/.dw/host-registry.json          # when implemented
DW-SuperApps/.dw/bindings/<project-id>/<power-id>.json
```

Registered projects must not receive `.dw/powers`, router files, or generated host adapters.

## Resolution order

For each Power invocation:

1. read root `AGENTS.md`;
2. resolve the target project from `workspace.yaml`;
3. confirm the Power is enabled;
4. read `DW-SuperApps/.dw/powers/<power-id>/MANIFEST.json`;
5. select one existing declared installed entrypoint;
6. use source submodule entrypoints only when no managed package exists and compatibility/development fallback is allowed;
7. write runtime and project configuration only under the target-owned runtime root.

Never resolve `<project>/.dw/powers/<power-id>` as the active package. Report it as `LEGACY_TARGET_INSTALL` and preserve it.

## No active-host switch

All configured native adapters may coexist. Switching IDEs must not require package reinstallation, runtime movement, target mutation, or package copying.

## Thin native adapters

Current compatibility surfaces:

```text
.codex/skills/<power>/SKILL.md
.kiro/skills/<power>/SKILL.md
.claude/skills/<power>/SKILL.md
.github/skills/<power>/SKILL.md
.github/copilot-instructions.md
.clinerules/00-dw-superapps.md
.kilo/rules/dw-superapps.md
.agents/skills/<power>/SKILL.md
```

All are rooted in DW-SuperApps. A wrapper contains routing metadata and references only. It must not copy Power implementation into a project.

The preferred future surface remains one logical `dw-super` router per host. Do not claim that router is implemented until `.dw/router/SKILL.md` and the host registry are generated and doctored.

## Adapter generation

```bash
./bin/dw host install all --mode wrapper
./bin/dw host status all
```

`wrapper` is the safe cross-platform default. `link` and `copy` are compatibility modes and still resolve the installed workspace package first.

## Deduplication

1. expose at most one logical DW identity per host;
2. do not generate the same skill in unrelated compatibility roots;
3. detect stale wrappers and broken installed entrypoints;
4. remove only generated duplicates;
5. never overwrite unmanaged host instructions;
6. projects must contain no generated DW host adapter payloads.

## BMAD

BMAD package code and host skills remain in DW-SuperApps. Project `.bmad`, `_bmad`, and `_bmad-output` remain in the selected project. Host bootstrap and project bootstrap are separate ownership phases.

## Doctor requirements

Doctor must report:

- workspace package store exists and is managed;
- installed package identity and declared entrypoint are valid;
- every configured workspace adapter exists;
- each adapter resolves the workspace package store before source fallback;
- no adapter points to a project `.dw/powers` path;
- no project contains generated host skill payloads;
- no duplicate logical identity or stale target exists;
- switching IDEs requires no state mutation;
- legacy target packages are reported and preserved.

Statuses:

- `READY`: packages, adapters, dedupe, and invocation pass;
- `PARTIAL`: packages work but router migration, adapter generation, or dedupe is incomplete;
- `BLOCKED`: safe activation cannot proceed because unmanaged or conflicting files exist;
- `FAILED`: an executed validation returned a real failure.
