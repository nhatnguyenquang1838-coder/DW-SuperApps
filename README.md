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

## OpenClaw ACPX orchestrator

OpenClaw can operate as the DW SUPER control plane and dispatch bounded work through ACPX to Codex, Claude Code, Kiro CLI, and Kilocode.

```bash
bash hosts/openclaw-acpx/install.sh
openclaw gateway restart
```

Windows PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1
openclaw gateway restart
```

The baseline is fail-closed: reads are approved, write or exec prompts fail when non-interactive approval is unavailable, and both OpenClaw MCP bridges remain disabled. See [`docs/OPENCLAW_ACPX_SETUP.md`](docs/OPENCLAW_ACPX_SETUP.md).

## Included Powers

| Power | Purpose | Default delivery |
|---|---|---|
| GWC | Governance and governed delivery | Validated Power distribution with submodule fallback |
| Understand Anything | Architecture and codebase knowledge graphs | Validated Power distribution with submodule fallback |
| Task Me | Impact analysis and implementation task planning | Validated Power distribution with submodule fallback |
| BMAD Method | Product analysis, planning, architecture, implementation, and review lifecycle | Release-first external Power |

Discover the registered Powers:

```bash
dw power list
dw power info gwc
dw power info ua
dw power info task-me
dw power info bmad
dw system powers rental-home
```

## BMAD Method Power

BMAD is packaged as a deterministic, skills-only Power from an exact commit of [`nhatnguyenquang1838-coder/BMAD-METHOD`](https://github.com/nhatnguyenquang1838-coder/BMAD-METHOD). The DW wrapper does not modify the BMAD source repository.

The distribution includes:

- BMAD core skills;
- the BMM software-delivery lifecycle;
- shared scripts and the official installer;
- a portable multi-host bootstrap;
- DW configuration and consumer contracts.

It excludes the BMAD website, dashboard/UI, evals, repository tests, generated web bundles, and consumer project data.

### Install BMAD into a project

Current published package:

```text
Release: bmad-main-bb45db4aa449
Version: main-bb45db4aa449
Source:  bb45db4aa4496c69239f9c0629c290fd1b072fc9
```

Install the immutable release into a consumer project:

```bash
dw power install bmad \
  --source release \
  --version main-bb45db4aa449 \
  --target /path/to/project
```

Bootstrap BMAD for Codex:

```bash
python /path/to/project/.dw/powers/bmad/distribution/lib/bootstrap_bmad.py \
  --target /path/to/project \
  --host codex
```

For Kiro, replace `codex` with `kiro`. Supported bootstrap hosts are `kiro`, `codex`, `copilot`, `cline`, `kilo`, `claude`, and `custom`.

Validate the installed package:

```bash
python /path/to/project/.dw/powers/bmad/lib/power_runtime.py \
  doctor --target /path/to/project
```

Generate a host-neutral BMAD instruction prompt:

```bash
dw power prompt bmad \
  --system rental-home \
  --task "Plan and deliver the next product change using the BMAD lifecycle"
```

Then use the installed `bmad-help` skill to identify the current lifecycle state and route to the appropriate BMAD skill.

BMAD distribution references:

- Release: [`bmad-main-bb45db4aa449`](https://github.com/nhatnguyenquang1838-coder/DW-SuperApps/releases/tag/bmad-main-bb45db4aa449)
- Distribution branch: [`power-dist-bmad`](https://github.com/nhatnguyenquang1838-coder/DW-SuperApps/tree/power-dist-bmad)
- Detailed guide: [`docs/powers/BMAD_POWER.md`](docs/powers/BMAD_POWER.md)

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
dw power prompt bmad --system rental-home --task "Route this change through the BMAD lifecycle"
```

## Layout

```text
powers/
  gwc/          Governance and delivery Power fallback
  ua/           Semantic knowledge Power fallback
  task-me/      Implementation planning Power fallback
  bmad/         Local router for the release-first BMAD Power
hosts/
  openclaw-acpx/ OpenClaw control-plane profile and ACPX worker contracts
plugins/
  bmad-method/  BMAD source lock, graph, package recipe, and DW overlay
systems/
  rental-home/  First product system
```

GWC, UA, and Task Me retain reviewed git submodules as migration and recovery fallbacks. BMAD is an external release-first Power and is not required to be a workspace submodule.

Runtime data remains owned by the consumer system repository:

```text
systems/rental-home/.ua/
systems/rental-home/.task-me/
systems/rental-home/.gwc/
systems/rental-home/.bmad/
```

See:

- [`docs/DW_SUPER_SETUP.md`](docs/DW_SUPER_SETUP.md)
- [`docs/POWER_RUNTIME_V2.md`](docs/POWER_RUNTIME_V2.md)
- [`docs/MULTI_HOST_SETUP.md`](docs/MULTI_HOST_SETUP.md)
- [`docs/OPENCLAW_ACPX_SETUP.md`](docs/OPENCLAW_ACPX_SETUP.md)
- [`docs/powers/BMAD_POWER.md`](docs/powers/BMAD_POWER.md)
