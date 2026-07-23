# DW SuperApps

Host-neutral engineering workspace for Kiro, Codex, reusable AI Powers, and multiple system repositories.

## One-click bootstrap

### macOS / Linux / Git Bash

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
./bin/dw init all
```

### Windows PowerShell

```powershell
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
.\dw.ps1 init all
```

## Daily commands

```bash
dw sync all
dw status all
dw doctor all
dw clean all
```

`dw clean all` removes only generated adapters and caches. Runtime data under system repositories is preserved unless `--include-runtime --yes` is explicitly supplied.

See [`docs/POWER_RUNTIME_V2.md`](docs/POWER_RUNTIME_V2.md) for all one-click, Kiro, Codex, and targeted commands.

## Layout

```text
powers/
  gwc/          Governance and delivery Power
  ua/           Semantic knowledge Power
  task-me/      Implementation planning Power
systems/
  rental-home/  First product system
.kiro/          Kiro host adapter
.codex/         Codex host adapter
```

Power and system repositories are pinned as Git submodules. Develop each Power in its own repository, then deliberately update the pin in this workspace.

Runtime data remains owned by the system repository:

```text
systems/rental-home/.ua/
systems/rental-home/.task-me/
systems/rental-home/.gwc/
```
