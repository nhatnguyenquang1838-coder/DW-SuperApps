# DW SuperApps

DW SuperApps is a host-neutral control workspace for reusable AI Powers, editable projects, product systems, model providers, and agent hosts.

## Choose your starting point

### Use this workspace

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
bash bin/dw install --shell auto --init

dw project list
dw power list
dw system list
dw doctor all
```

### Create another Super Project

Run from an initialized DW-SuperApps checkout:

```bash
dw workspace init ../my-super-project \
  --id my-super-project \
  --name "My Super Project"

cd ../my-super-project
bash bin/dw install --shell auto
```

The initializer copies the governed DW runtime and manifests, creates an empty generic project registry, prepares the workspace-owned package inbox, and initializes Git. It does not copy product repositories, installed Power packages, runtime data, credentials, or generated host adapters.

Add the first product project:

```bash
dw project add rental-home \
  --repo nhatnguyenquang1838-coder/rental_home \
  --role product \
  --role system \
  --system \
  --enable-powers gwc,ua,task-me,bmad
```

Review and validate:

```bash
git diff -- .gitmodules workspace.yaml
dw project list
dw validate
dw doctor all --offline
```

### Initialize an existing management repository

```bash
cd existing-super-project
dw workspace init . \
  --id existing-super-project \
  --name "Existing Super Project" \
  --in-place
```

Initialization is non-destructive and refuses to replace an existing `workspace.yaml` or managed runtime path.

## Core model

```text
projects/*                    editable Git project repositories
manifests/powers/*            logical Power contracts and routing metadata
.dw/powers/*                  installed validated Power packages
.dw/bindings/*                project/system-to-package bindings
<project>/.gwc                GWC runtime and configuration
<project>/.ua                 UA runtime and knowledge
<project>/.task-me            Task Me runtime and plans
<project>/.bmad               BMAD project configuration
host adapter roots            thin workspace-owned routing only
```

All editable source repositories live below `projects/*`. Root `powers/` contains only non-submodule routing assets, while installed packages remain under `.dw/powers/*`.

## Project commands

```bash
dw project list
dw project info rental-home
dw project add <project-id> --repo <owner/repository> --role product
```

`dw project add` creates a Git submodule and updates `workspace.yaml`. It never installs a Power package or writes project runtime data.

## Power commands

```bash
dw power list
dw power info gwc
dw power install gwc --source auto --target projects/rental-home
dw power sanity gwc
dw power doctor gwc --target projects/rental-home
/dw-gwc Review delivery scope
```

Power packages belong to the Super Project package store. Runtime and project configuration belong to the selected project/system.

## Supported hosts

Kiro, Codex, GitHub Copilot, Cline, Kilo Code, Claude Code, and custom agents are supported through thin adapters. Ollama is registered separately as an OpenAI-compatible model provider.

```bash
dw host install all --mode wrapper
dw host status all
dw provider status all
```

## Installation guides

- [Installation index](docs/installation/README.md)
- [Create a Super Project](docs/installation/CREATE_SUPER_PROJECT.md)
- [Add a project or system](docs/installation/ADD_PROJECT.md)
- [Install Powers](docs/installation/INSTALL_POWERS.md)
- [Offline installation](docs/installation/OFFLINE_INSTALL.md)
- [Migrate an existing workspace](docs/installation/MIGRATION.md)
- [Troubleshooting](docs/installation/TROUBLESHOOTING.md)

## Daily operations

```bash
dw status all
dw sync all
dw doctor all
dw clean all
```

`dw clean all` removes generated adapters and caches only. Runtime data is preserved unless destructive runtime cleanup is explicitly authorized with `--include-runtime --yes`.

## Orchestration

GWC is the primary governance workflow. DW SuperApps can orchestrate worker
powers when G1 hooks match task intents.

```bash
dw orchestrator prompt --system rental-home --task "Plan implementation tasks for user authentication"
dw orchestrator run --system rental-home --task "Design service boundaries for notification system"
```

- `prompt` returns a composed human-readable prompt.
- `run` returns a structured JSON execution plan with ordered phases.

## Reports

Generate user-facing Markdown reports from GWC gate artifacts.

```bash
dw report g1 --workspace .gwc/tasks/<task-id>
```

Currently supported:
- `g1` — alignment report from `g1-intake-brief.yaml`, `g1-options.yaml`, `g1-preflight-report.yaml`, and `g1-decision-record.yaml`

## Current Powers

| Power | Purpose | Default delivery |
|---|---|---|
| GWC | Governance and governed delivery | Validated distribution; source project available for development |
| Understand Anything | Architecture and semantic codebase knowledge | Validated distribution; controlled source project under `projects/ua` |
| Task Me | Impact analysis and implementation planning | Validated distribution; source project available for development |
| BMAD Method | Product and delivery lifecycle workflows | Release-first external Power |

## Child-project independence

Standalone project contracts and direct Power injection without a parent Super Project are tracked separately in GitHub Issue #15. The current Super Project bootstrap does not move package-store ownership into child projects.
