# DW SuperApps

Host-neutral engineering workspace for reusable AI Powers, multiple product systems, local model providers, and agent hosts.

## One-click bootstrap

### Bash / Zsh / Linux / macOS / Git Bash

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
bash bin/dw install --shell auto --init
```

Reload the shell, then verify:

```bash
dw --version
dw host status all
dw provider status all
dw doctor all
```

The Bash launcher automatically resolves `python3`, `python`, or `py -3`.

### Windows PowerShell

```powershell
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
.\dw.ps1 init all
```

## Supported hosts

```text
Kiro
Codex
GitHub Copilot
Cline
Kilo Code
Claude Code
Custom/Bionics-style agents
```

Ollama is registered separately as an OpenAI-compatible model provider.

```bash
dw host list
dw host install all
dw provider install ollama --model qwen3-coder:30b
```

## Daily commands

```bash
dw sync all
dw status all
dw doctor all
dw clean all
```

`dw clean all` removes generated adapters and caches only. Runtime data under system repositories is preserved unless `--include-runtime --yes` is supplied.

## Power invocation

```bash
dw power prompt ua --system rental-home --task "Analyze architecture"
dw power prompt task-me --system rental-home --task "Create an implementation plan"
dw power prompt gwc --system rental-home --task "Review delivery scope"
```

## Layout

```text
powers/
  gwc/          Governance and delivery Power
  ua/           Semantic knowledge Power
  task-me/      Implementation planning Power
systems/
  rental-home/  First product system
```

Power and system repositories are pinned Git submodules. Runtime data remains owned by the system repository:

```text
systems/rental-home/.ua/
systems/rental-home/.task-me/
systems/rental-home/.gwc/
```

See:

- `docs/POWER_RUNTIME_V2.md`
- `docs/MULTI_HOST_SETUP.md`
