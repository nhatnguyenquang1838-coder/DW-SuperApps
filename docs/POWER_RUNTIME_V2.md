# DW SuperApps Power Runtime v2.1

## One-click commands

Run from the `DW-SuperApps` root.

### macOS / Linux / Git Bash

```bash
./bin/dw init all
./bin/dw sync all
./bin/dw status all
./bin/dw doctor all
./bin/dw clean all
```

### Windows PowerShell

```powershell
.\dw.ps1 init all
.\dw.ps1 sync all
.\dw.ps1 status all
.\dw.ps1 doctor all
.\dw.ps1 clean all
```

### Windows Command Prompt

```bat
dw.cmd init all
dw.cmd sync all
dw.cmd status all
dw.cmd doctor all
dw.cmd clean all
```

## Command behavior

| Command | One-click behavior |
|---|---|
| `dw init all` | Install development dependencies, initialize every Power and system submodule, install Kiro and Codex adapters, validate the workspace. |
| `dw sync all` | Refuse dirty submodules, update every submodule to its configured remote branch, refresh adapters, validate. Does not stage or commit pins. |
| `dw sync all --pin` | Run the normal sync and stage reviewed gitlink changes. Still does not commit. |
| `dw status all` | Show workspace registration, recursive submodule status, and host-adapter readiness. |
| `dw doctor all` | Validate the workspace, inspect remote drift and dirty state, and verify adapters. |
| `dw doctor all --offline` | Run health checks without remote drift lookup. |
| `dw clean all` | Remove generated Kiro/Codex adapters and workspace caches. Preserve `.ua`, `.task-me`, and `.gwc` runtime data. |
| `dw clean all --include-runtime --yes` | Also remove system-owned runtime data. This is destructive. |
| `dw reset all --yes` | Refuse dirty submodules, deinitialize all clean submodules, and remove generated adapters/caches. Rebuild with `dw init all`. |

## Common daily flow

```bash
dw status all
dw sync all
dw doctor all
```

To stage updated submodule pins for review:

```bash
dw sync all --pin
git diff --cached --submodule=short
```

## Targeted commands

```bash
dw init powers
dw sync task-me
dw sync rental-home
dw doctor powers
dw reset rental-home --yes
```

Valid targets are:

```text
all
powers
systems
gwc
ua
task-me
rental-home
```

## Entry commands

```bash
dw --version
dw workspace info
dw power list
dw power info ua
dw system list
dw system powers rental-home
```

Use `./bin/dw`, `.\dw.ps1`, or `dw.cmd` when `dw` is not on `PATH`.

## Kiro setup

```bash
dw init all --host kiro
dw host status kiro
```

Open the `DW-SuperApps` root in Kiro. Generate a Power prompt:

```bash
dw power prompt ua \
  --system rental-home \
  --task "Analyze the current architecture and refresh the project knowledge graph"
```

## Codex IDE setup

```powershell
.\dw.ps1 init all --host codex
.\dw.ps1 host status codex
```

Open the `DW-SuperApps` root in Codex. Generate a Power prompt:

```powershell
.\dw.ps1 power prompt task-me `
  --system rental-home `
  --task "Create an implementation plan for OPS-LEASE"
```

## Low-level lifecycle commands

The original granular commands remain available:

```bash
dw power init all
dw power status all
dw power check all
dw power update task-me
dw power pin task-me
dw host install all --mode wrapper
dw host status all
dw validate
```

`update` refuses dirty submodules. `pin` stages reviewed gitlinks and never commits.

## Validation

```bash
dw validate
python -m unittest discover -s tests -p "test_*.py"
```
