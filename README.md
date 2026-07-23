# DW SuperApps

Host-neutral engineering workspace for Kiro, Codex, reusable AI Powers, and multiple system repositories.

## Bootstrap

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
git submodule update --init --recursive
```

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
