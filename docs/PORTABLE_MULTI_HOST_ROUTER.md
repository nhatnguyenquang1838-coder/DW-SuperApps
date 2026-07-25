# Portable Multi-Host Router Contract

## Goal

Allow a user to open the same DW SUPER project in Codex, Kiro, Kilo Code, GitHub Copilot, Claude Code, Cline, or a custom host without reinstalling Powers or changing a global active-host setting.

The design must optimize both:

- **user portability:** switch IDEs by opening the same project;
- **host efficiency:** expose one DW routing surface and load only the selected Power workflow.

## Core model

```text
one target project
  -> one managed Power store
  -> one canonical DW router
  -> thin native adapters for all configured hosts
```

Canonical locations:

```text
<target-project>/.dw/powers/<power-id>/
<target-project>/.dw/router/SKILL.md
<target-project>/.dw/host-registry.json
```

Host folders are discovery surfaces only. They must not become additional sources of Power logic.

## No active-host switch

Portable setup does not maintain a mutable global state such as:

```text
active_host = codex
```

All configured native adapters may coexist. Each IDE discovers its own adapter naturally when the project is opened.

Switching IDEs must not require:

- reinstalling Powers;
- regenerating runtime data;
- changing the target system;
- activating or deactivating another host;
- copying prompts manually;
- changing canonical package content.

## Canonical router

The portable target is one skill identity:

```text
dw-super
```

The router should contain only routing logic and references. It should not duplicate GWC, UA, Task Me, or BMAD implementation content.

Required routing:

| Intent | Power |
|---|---|
| Governance, gates, approvals, delivery control | GWC |
| Architecture, semantic graph, dependency analysis | UA |
| Impact analysis, implementation planning, coding guidance | Task Me |
| Structured product/spec/implementation workflow | BMAD |
| Install, update, offline ZIP, activation, doctor | Power Dist onboarding runbook |

Router execution order:

1. read root `AGENTS.md`;
2. resolve the target from `workspace.yaml`;
3. confirm the selected Power is enabled;
4. read the installed package `MANIFEST.json`;
5. select one existing declared entrypoint;
6. load only that Power workflow;
7. write output only to the target-owned runtime root.

## Thin native adapters

Preferred future layout:

```text
.codex/skills/dw-super/SKILL.md
.kiro/skills/dw-super/SKILL.md
.claude/skills/dw-super/SKILL.md
.kilo/skills/dw-super/SKILL.md
.github/copilot-instructions.md
.clinerules/00-dw-superapps.md
```

A native wrapper should contain only:

- skill metadata required by the host;
- a reference to root `AGENTS.md`;
- a reference to `.dw/router/SKILL.md`;
- a prohibition against copying or modifying canonical Power content.

Example conceptual wrapper:

```markdown
---
name: dw-super
description: Route DW SUPER installation, governance, architecture, implementation planning, and BMAD workflows.
---

Read root `AGENTS.md`, then read `.dw/router/SKILL.md`.
Load only the selected installed Power entrypoint.
Do not duplicate or modify canonical Power content.
```

Use generated wrappers rather than symlinks as the safe cross-platform default, especially on Windows.

## Compatibility-root deduplication

Some hosts scan compatibility folders belonging to other hosts. A portable setup must prevent one host from seeing multiple DW skills with the same logical identity.

Rules:

1. publish at most one discoverable `dw-super` identity per host;
2. do not create the same DW skill under every compatibility root merely because a host can read them;
3. when one native root can serve two hosts safely, share it rather than duplicate it;
4. isolate or disable external compatibility roots when they create duplicate discovery;
5. do not place a generic `.agents/skills/dw-super` adapter unless a custom host actually requires it;
6. ensure generated adapters declare the same canonical router identity and version;
7. detect stale adapters whose target no longer matches `.dw/router/SKILL.md`.

## Host guidance

### Codex

Native discovery root:

```text
.codex/skills/dw-super/SKILL.md
```

Root `AGENTS.md` remains the global policy. The adapter points to the canonical router.

### Kiro

Native discovery root:

```text
.kiro/skills/dw-super/SKILL.md
```

Persistent project guidance belongs in root policy or Kiro steering; Power implementation remains canonical under `.dw/powers`.

### Claude Code

Native discovery root:

```text
.claude/skills/dw-super/SKILL.md
```

`CLAUDE.md` should import or route to root `AGENTS.md`; it should not copy the full policy.

### GitHub Copilot

Keep `.github/copilot-instructions.md` as a short routing index. Avoid publishing the same DW skill simultaneously under every Copilot-compatible skill root.

When a shared Claude/Copilot skill root is used, doctor must verify that Copilot sees one logical `dw-super` identity only.

### Kilo Code

Prefer a native Kilo rule or skill that points to the canonical router. If Kilo also scans `.claude/skills` or `.agents/skills`, configure isolation so only one DW router is visible.

Do not assume every Kilo installation uses the same compatibility settings. Doctor the actual effective discovery sources.

### Cline

Use a short `.clinerules/00-dw-superapps.md` routing file. Do not copy Power workflows into `.clinerules`.

### Custom hosts

Use `.agents/` only when the actual host is configured to read it. Generic compatibility folders should not be generated by default merely as a fallback.

## Host registry

The target portable registry should record generated state:

```json
{
  "schemaVersion": 1,
  "profile": "portable",
  "canonicalRouter": ".dw/router/SKILL.md",
  "hosts": {
    "codex": {"adapter": ".codex/skills/dw-super/SKILL.md"},
    "kiro": {"adapter": ".kiro/skills/dw-super/SKILL.md"},
    "claude": {"adapter": ".claude/skills/dw-super/SKILL.md"},
    "copilot": {"adapter": ".github/copilot-instructions.md"},
    "kilo": {"adapter": ".kilo/skills/dw-super/SKILL.md"},
    "cline": {"adapter": ".clinerules/00-dw-superapps.md"}
  }
}
```

The registry is generated evidence, not an authority source. Canonical package manifests and repository instructions remain authoritative.

## Doctor requirements

Portable host doctor must report:

- canonical router exists and is managed;
- every configured native adapter exists;
- every adapter resolves the same router;
- no adapter embeds copied Power implementation content;
- no duplicate `dw-super` identity is visible to a host;
- no duplicate Power identity is visible through compatibility roots;
- no stale or broken adapter target exists;
- no unexpected generic compatibility adapter exists;
- each installed Power has one valid manifest-declared entrypoint;
- switching IDEs requires no state mutation.

Statuses:

- `READY`: router, adapters, dedupe, package entrypoints, and invocation pass;
- `PARTIAL`: packages work but router migration, adapter generation, or dedupe is incomplete;
- `BLOCKED`: safe activation cannot proceed because unmanaged or conflicting host files exist;
- `FAILED`: an executed validation returned a real failure.

## Current-runtime compatibility

The checked-out runtime may still generate one adapter per Power for each host. Documentation must not claim the canonical router is implemented until runtime code provides it.

Until router implementation exists:

1. install Powers canonically under `.dw/powers`;
2. allow configured host adapters to coexist;
3. load only one selected Power entrypoint per task;
4. inspect the effective host discovery roots for duplicates;
5. remove only generated duplicates, never unmanaged host files;
6. report portable-router implementation as pending;
7. do not invent commands such as `dw setup portable` or `dw host sync portable`.

The future runtime should replace the current `host x every Power` generation model with `host x one DW router`, but that code change is outside this documentation-only contract.
