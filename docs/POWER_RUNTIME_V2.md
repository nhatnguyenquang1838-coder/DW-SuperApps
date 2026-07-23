# DW SuperApps Power Runtime v2

## Entry commands

### macOS / Linux / Git Bash

```bash
./bin/dw --version
./bin/dw workspace info
```

### Windows PowerShell

```powershell
.\dw.ps1 --version
.\dw.ps1 workspace info
```

### Windows Command Prompt

```bat
dw.cmd --version
dw.cmd workspace info
```

## Workspace and discovery

```bash
dw workspace info
dw power list
dw power info ua
dw system list
dw system powers rental-home
```

Use `./bin/dw`, `.\dw.ps1`, or `dw.cmd` in place of `dw` when the repository command is not on `PATH`.

## Submodule lifecycle

```bash
dw power init
dw power status
dw power check all
dw power update task-me
dw power pin task-me
```

`update` refuses dirty submodules. `pin` stages only reviewed gitlinks and does not commit.

## Kiro setup

Run from the DW-SuperApps root:

```bash
dw power init
dw host install kiro
dw host status kiro
```

Open `DW-SuperApps` as the Kiro workspace. Kiro discovers generated adapters under:

```text
.kiro/skills/gwc/
.kiro/skills/ua/
.kiro/skills/task-me/
```

Generate a complete prompt:

```bash
dw power prompt ua \
  --system rental-home \
  --task "Analyze the current architecture and refresh the project knowledge graph"
```

Paste the output into Kiro chat. Direct prompts also work:

```text
Use the UA Power for rental-home. Analyze the current architecture and refresh system-owned .ua data.
```

```text
Use the Task Me Power for rental-home. Create an impact analysis and implementation plan for OPS-LEASE.
```

```text
Use the GWC Power for rental-home only for governance and delivery control explicitly requested by this task.
```

## Codex IDE setup

Run from the DW-SuperApps root:

```powershell
.\dw.ps1 power init
.\dw.ps1 host install codex
.\dw.ps1 host status codex
```

Open the **DW-SuperApps root**, not only the Rental Home submodule. Codex reads the root `AGENTS.md`, the system-local instructions, and generated adapters under:

```text
.codex/skills/gwc/
.codex/skills/ua/
.codex/skills/task-me/
```

Generate and paste a Codex-ready prompt:

```powershell
.\dw.ps1 power prompt task-me `
  --system rental-home `
  --task "Create an implementation plan for OPS-LEASE"
```

A direct Codex request can be:

```text
Use the task-me Power registered in workspace.yaml for system rental-home. Read the canonical Power entrypoint and generate outputs only under systems/rental-home/.task-me/.
```

## Adapter modes

Cross-platform wrappers are the default:

```bash
dw host install all --mode wrapper
```

Optional modes:

```bash
dw host install kiro --mode link
dw host install codex --mode copy
```

`wrapper` is recommended on Windows because it does not require symlink privileges. Power logic remains in the pinned submodule.

## Validation

```bash
dw validate
python -m unittest discover -s tests -p "test_*.py"
```
