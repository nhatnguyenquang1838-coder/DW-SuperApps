# DW SuperApps Multi-Host Setup

DW SuperApps exposes the same Power contracts to multiple AI hosts without copying Power logic.

## Supported hosts

| Host | Generated adapter |
|---|---|
| Kiro | `.kiro/skills/<power>/SKILL.md` |
| Codex | `.codex/skills/<power>/SKILL.md` |
| GitHub Copilot | `.github/instructions/dw-superapps.instructions.md` |
| Cline | `.clinerules/00-dw-superapps.md` |
| Kilo Code | `.kilo/rules/dw-superapps.md` + `kilo.jsonc` |
| Claude Code | `CLAUDE.md` + `.claude/skills/<power>/SKILL.md` |
| Custom/Bionics-style agent | `.agents/DW_AGENT.md` + `.agents/skills/<power>/SKILL.md` |

Aliases `bionics`, `biotic`, and `ollama` resolve to the generic `custom` host.

## One-click initialization

Bash, Zsh, Linux, macOS, or Git Bash:

```bash
git pull
bash bin/dw install --shell auto --init
source ~/.bashrc 2>/dev/null || source ~/.zshrc
```

The installer:

1. Registers the global `dw` command.
2. Installs dependencies.
3. Initializes all Power and system submodules.
4. Generates adapters for every configured host.
5. Generates the Ollama OpenAI-compatible provider profile.
6. Validates the workspace.

Verify:

```bash
dw host list
dw host status all
dw provider status all
dw doctor all
```

## Targeted host setup

```bash
dw host install copilot
dw host install cline
dw host install kilo
dw host install claude
dw host install custom
dw host install bionics
```

Skill-based hosts support adapter modes:

```bash
dw host install kiro --mode wrapper
dw host install codex --mode link
dw host install claude --mode copy
```

`wrapper` is the safest cross-platform default.

## Ollama compatibility

DW registers Ollama as an OpenAI-compatible provider using:

```text
Base URL: http://localhost:11434/v1
API key:  ollama
```

Default setup:

```bash
dw provider install ollama
dw provider status ollama
```

The default local coding model is:

```text
qwen3-coder:30b
```

Select a model explicitly:

```bash
dw provider install ollama --model qwen3-coder:30b
```

Or use an environment variable:

```bash
export OLLAMA_MODEL=your-model-tag
dw init all
```

Probe the running Ollama API:

```bash
dw provider status ollama --probe
```

Generated profile:

```text
.agents/providers/ollama.json
.agents/providers/ollama.env.example
```

Use the same values in Cline, Kilo, Copilot-compatible clients, or a custom agent that accepts an OpenAI-compatible endpoint.

## Calling a Power

Host-neutral prompt generation:

```bash
dw power prompt ua \
  --system rental-home \
  --task "Analyze architecture and refresh project knowledge"
```

```bash
dw power prompt task-me \
  --system rental-home \
  --task "Create impact analysis and an implementation plan"
```

```bash
dw power prompt gwc \
  --system rental-home \
  --task "Review delivery scope and validation evidence"
```

Paste the generated prompt into any supported host. Custom agents may read `.agents/DW_AGENT.md` directly.

## Host-specific notes

### GitHub Copilot

Open the DW-SuperApps repository root. Copilot loads `AGENTS.md` and the generated path-specific instructions.

### Cline

Open the repository root. Cline detects `AGENTS.md` and `.clinerules/00-dw-superapps.md`.

### Kilo Code

Open the repository root. Kilo reads `AGENTS.md`; the generated `kilo.jsonc` also points to `.kilo/rules/*.md`.

### Claude Code

Run from the repository root:

```bash
claude
```

The generated root `CLAUDE.md` imports `AGENTS.md` and routes Claude to the Power manifests.

### Custom or Bionics-style agents

Configure the agent to read:

```text
AGENTS.md
workspace.yaml
.agents/DW_AGENT.md
.agents/skills/
```

For local Ollama inference, use the generated provider JSON or the OpenAI-compatible endpoint above.

## Cleanup

Safe cleanup preserves project runtime data:

```bash
dw clean all
```

Rebuild all adapters:

```bash
dw host install all
```

Destructive runtime cleanup still requires explicit confirmation:

```bash
dw clean all --include-runtime --yes
```
