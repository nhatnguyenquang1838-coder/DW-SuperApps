# DW SuperApps Operations

## First setup

```bash
git clone --recurse-submodules https://github.com/nhatnguyenquang1838-coder/DW-SuperApps.git
cd DW-SuperApps
python3 -m pip install -r requirements-dev.txt
bash scripts/install-host-adapters.sh
python3 scripts/validate-workspace.py
```

## Daily Power development

Develop and merge changes inside the source Power repository first. Then update the workspace pin deliberately.

```bash
# Move Task Me working copy to latest main
bash scripts/sync-submodules.sh update task-me

# Inspect pin and remote drift
bash scripts/sync-submodules.sh check task-me

# Stage the new gitlink only after review
bash scripts/sync-submodules.sh pin task-me

git commit -m "chore: update Task Me Power pin"
```

The same workflow applies to `gwc`, `ua`, `rental-home`, `powers`, `systems`, or `all`.

## Unified command

```bash
bash bin/dw power init
bash bin/dw power check
bash bin/dw power update gwc
bash bin/dw power pin gwc
bash bin/dw host install
bash bin/dw validate
bash bin/dw system list
```

## Safety behavior

- `update` refuses to move a dirty submodule.
- `pin` refuses to stage a dirty submodule.
- No script creates a commit, pushes, merges, or changes a remote repository.
- Runtime data stays in the owning system repository: `.ua/`, `.task-me/`, and `.gwc/`.
- Kiro and Codex adapters are generated links; canonical Power behavior stays in `powers/`.

## Rental Home flow

```text
systems/rental-home
  -> powers/ua       builds or refreshes .ua
  -> powers/task-me  produces .task-me plans
  -> powers/gwc      applies governance only when explicitly activated
```
