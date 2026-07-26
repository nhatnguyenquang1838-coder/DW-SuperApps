# DW SuperApps Multi-Host Setup

DW-SuperApps owns one shared set of installed Powers and all host adapters. Registered systems own only their runtime and project configuration.

## Layout

```text
DW-SuperApps/.dw/powers/<power-id>/
DW-SuperApps/.codex/...
DW-SuperApps/.kiro/...
DW-SuperApps/.claude/...
DW-SuperApps/.github/...
DW-SuperApps/.kilo/...
DW-SuperApps/.clinerules/...
DW-SuperApps/.agents/...
projects/rental-home/.gwc | .ua | .task-me | .bmad | _bmad*
```

Do not generate Power packages or host adapters inside `projects/rental-home`.

## Install packages for a system

```bash
./bin/dw power install gwc --source auto --target projects/rental-home
./bin/dw power install ua --source auto --target projects/rental-home
./bin/dw power install task-me --source auto --target projects/rental-home
```

`--target` selects the runtime target. The package store comes from `workspace.yaml > distribution.storeRoot`.

## Generate adapters

```bash
./bin/dw host install all --mode wrapper
./bin/dw host status all
```

The adapter resolver prefers installed package entrypoints from `.dw/powers/<power-id>/`. Source submodules are compatibility fallbacks only.

Current adapter roots:

| Host | Workspace adapter |
|---|---|
| Kiro | `.kiro/skills/<power>/SKILL.md` |
| Codex | `.codex/skills/<power>/SKILL.md` |
| GitHub Copilot | `.github/copilot-instructions.md` and `.github/skills/<power>/SKILL.md` |
| Cline | `.clinerules/00-dw-superapps.md` |
| Kilo Code | `.kilo/rules/dw-superapps.md` and `kilo.jsonc` |
| Claude Code | `CLAUDE.md` and `.claude/skills/<power>/SKILL.md` |
| Custom | `.agents/DW_AGENT.md` and `.agents/skills/<power>/SKILL.md` |

## Call a Power

```bash
dw power prompt ua --system rental-home --task "Analyze architecture"
dw power prompt task-me --system rental-home --task "Create an implementation plan"
dw power prompt gwc --system rental-home --task "Review governance and evidence"
```

Prompt output displays:

- workspace root;
- package store and installed package;
- resolved entrypoint and fallback mode;
- target system path;
- runtime root;
- legacy target-install probe.

## Legacy installations

If `projects/rental-home/.dw/powers/<power-id>` exists, commands report `LEGACY_TARGET_INSTALL`. The path is not executed, overwritten, migrated, or deleted.

## BMAD split

- package and host skills: DW-SuperApps;
- `.bmad`, `_bmad`, `_bmad-output`, and project configuration: target system.

## Validation

```bash
python -m unittest discover -s tests -p "test_*.py"
./bin/dw validate
./bin/dw doctor all --offline
```

Verify that no host adapter or `.dw/powers` directory was created under a system.
