# DW SuperApps Multi-Host Setup

DW-SuperApps owns one shared set of installed Powers and all host adapters. Registered projects own only their runtime and project configuration.

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

## Install packages for a project

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

## Activate a Power

Use the native skill alias in the configured host and put the task after it:

```text
/dw-gwc Review governance and evidence
/dw-ua Analyze architecture
/dw-task-me Create an implementation plan
/dw-bmad Refine the product specification
```

The selected adapter resolves the target project and canonical installed entrypoint directly. No terminal command or generated task prompt is required.

## Legacy installations

If `projects/rental-home/.dw/powers/<power-id>` exists, commands report `LEGACY_TARGET_INSTALL`. The path is not executed, overwritten, migrated, or deleted.

## BMAD split

- package and host skills: DW-SuperApps;
- `.bmad`, `_bmad`, `_bmad-output`, and project configuration: target project.

## Validation

```bash
python -m unittest discover -s tests -p "test_*.py"
./bin/dw validate
./bin/dw doctor all --offline
```

Verify that no host adapter or `.dw/powers` directory was created under a project target.
