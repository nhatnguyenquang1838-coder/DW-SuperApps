# DW SuperApps

Host-neutral engineering workspace for Kiro, Codex, reusable AI Powers, and multiple system repositories.

## Bootstrap

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
python3 -m pip install -r requirements-dev.txt
./bin/dw power init
./bin/dw host install all
./bin/dw validate
```

Windows PowerShell:

```powershell
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
python -m pip install -r requirements-dev.txt
.\dw.ps1 power init
.\dw.ps1 host install all
.\dw.ps1 validate
```

## Power Runtime v2

```bash
./bin/dw workspace info
./bin/dw power list
./bin/dw power info task-me
./bin/dw system powers rental-home
./bin/dw power prompt task-me --system rental-home --task "Create an implementation plan"
```

See `docs/POWER_RUNTIME_V2.md` for Kiro, Codex IDE, adapter, prompt, and submodule commands.

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
