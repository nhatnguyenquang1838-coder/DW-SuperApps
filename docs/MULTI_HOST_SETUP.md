# DW SuperApps Multi-Host Setup

DW SuperApps supports multiple AI hosts over one canonical set of installed Powers.

For the target architecture and deduplication rules, read:

- `docs/PORTABLE_MULTI_HOST_ROUTER.md`

For package onboarding, including offline ZIP installation, read:

- `docs/runbooks/POWER_DIST_ONBOARDING.md`

## User experience goal

A user should be able to open the same project in Codex, Kiro, Kilo Code, GitHub Copilot, Claude Code, Cline, or a configured custom host without:

- reinstalling Powers;
- changing a global active-host value;
- moving runtime data;
- copying Power implementation into host folders;
- manually pasting a different setup prompt for each IDE.

All configured native adapters may coexist. Each host should discover one logical DW routing identity and load only the selected Power workflow.

## Current runtime adapters

The checked-out runtime currently defines these host roots:

| Host | Current generated adapter |
|---|---|
| Kiro | `.kiro/skills/<power>/SKILL.md` |
| Codex | `.codex/skills/<power>/SKILL.md` |
| GitHub Copilot | `.github/copilot-instructions.md` + `.github/skills/<power>/SKILL.md` |
| Cline | `.clinerules/00-dw-superapps.md` |
| Kilo Code | `.kilo/rules/dw-superapps.md` + `kilo.jsonc` |
| Claude Code | `CLAUDE.md` + `.claude/skills/<power>/SKILL.md` |
| Custom | `.agents/DW_AGENT.md` + `.agents/skills/<power>/SKILL.md` |

Aliases `bionics`, `biotic`, and `ollama` currently resolve to the generic `custom` host. Ollama is a model provider, not a host.

The current generator creates one adapter per Power. This is a compatibility implementation, not the final portable router model.

## Portable target

The preferred target is:

```text
one canonical Power store
  -> one canonical `dw-super` router
  -> one thin native adapter per configured host
```

Preferred future discovery surfaces:

```text
.codex/skills/dw-super/SKILL.md
.kiro/skills/dw-super/SKILL.md
.claude/skills/dw-super/SKILL.md
.kilo/skills/dw-super/SKILL.md
.github/copilot-instructions.md
.clinerules/00-dw-superapps.md
```

Do not claim this router is implemented until the checked-out runtime creates and doctors `.dw/router/SKILL.md` and its host registry.

Until then:

1. use the existing host generator;
2. keep Power implementation canonical;
3. load only one selected Power entrypoint per task;
4. doctor duplicate skill identities and compatibility-root leakage;
5. remove only generated duplicates;
6. never overwrite unmanaged host instructions;
7. report portable-router migration as pending.

## Current host commands

These commands are supported by the current workspace runtime:

```bash
dw host list
dw host status all
dw doctor all
```

Target one host:

```bash
dw host install kiro --mode wrapper
dw host install codex --mode wrapper
dw host install copilot --mode wrapper
dw host install claude --mode wrapper
dw host install cline
dw host install kilo
dw host install custom
```

`wrapper` is the safest cross-platform mode, especially on Windows.

Generate all currently configured adapters once:

```bash
dw host install all --mode wrapper
```

Generating all adapters does not mean every host should load every compatibility root. Doctor the effective discovery roots for each host.

Do not use hypothetical commands such as `dw setup portable`, `dw host sync portable`, or `dw host deactivate --all-except` unless they are implemented in the checked-out runtime.

## Host-specific guidance

### Codex

Open the project root. Root `AGENTS.md` provides global policy. Current adapters live under `.codex/skills`; the portable target is one `dw-super` wrapper.

### Kiro

Open the project root. Current adapters live under `.kiro/skills`; the portable target is one `dw-super` wrapper.

### GitHub Copilot

Open the project root. Keep `.github/copilot-instructions.md` as a short router. Avoid publishing duplicate DW skill identities in every Copilot-compatible skill root.

### Claude Code

Run Claude from the project root. `CLAUDE.md` should import or route to `AGENTS.md`; it should not copy the complete policy.

### Kilo Code

Open the project root. Kilo may read native rules plus compatibility roots depending on local configuration. Verify its effective skill sources and isolate external roots when they create duplicate DW identities.

### Cline

Use `.clinerules/00-dw-superapps.md` as a short routing file. Do not copy Power workflows into `.clinerules`.

### Custom hosts

Generate `.agents` content only when the actual custom host needs that root. Do not create generic compatibility adapters merely as a fallback.

## Calling a Power

Host-neutral prompt generation remains supported:

```bash
dw power prompt ua \
  --system rental-home \
  --task "Analyze architecture and refresh project knowledge"

dw power prompt task-me \
  --system rental-home \
  --task "Create impact analysis and an implementation plan"

dw power prompt gwc \
  --system rental-home \
  --task "Review delivery scope and validation evidence"
```

Reusable onboarding prompts are maintained separately:

- `prompts/power-dist/onboard.md`
- `prompts/power-dist/onboard-offline-zip.md`

## Provider compatibility

Ollama OpenAI-compatible defaults:

```text
Base URL: http://localhost:11434/v1
API key:  ollama
```

Current provider commands:

```bash
dw provider install ollama
dw provider status ollama
dw provider status ollama --probe
```

Provider configuration must not contain real secrets.

## Cleanup

Safe generated-adapter cleanup must preserve target runtime data.

```bash
dw clean all
```

Destructive runtime cleanup requires explicit authorization:

```bash
dw clean all --include-runtime --yes
```

After regeneration, validate:

- current host adapter exists;
- adapter target is current;
- one canonical Power entrypoint is selected;
- no duplicate DW identity is visible through compatibility roots;
- no unmanaged host file was overwritten;
- switching IDEs requires no project-state mutation.
