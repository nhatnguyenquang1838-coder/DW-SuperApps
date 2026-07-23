# DW SuperApps

Host-neutral engineering workspace for Kiro, Codex, reusable AI Powers, and multiple system repositories.

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

Power source repositories and system repositories are pinned as Git submodules. Runtime and generated data remain owned by each system repository.
