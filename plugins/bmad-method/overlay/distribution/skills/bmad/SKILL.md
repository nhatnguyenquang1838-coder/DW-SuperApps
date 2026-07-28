---
name: bmad
description: Bootstrap and route the BMAD Method software-delivery lifecycle inside a DW SuperApps consumer project.
---

# BMAD Method Power

This package contains the pinned BMAD core and BMM skill sources plus the official installer. It contains no dashboard, website, generated task, generated plan, or project runtime data.

## Start

1. Resolve the consumer project root.
2. If `<project-root>/_bmad` is missing, run:

   ```bash
   python <power-root>/distribution/lib/bootstrap_bmad.py \
     --target <project-root> \
     --host <kiro|codex|copilot|cline|kilo|claude|custom>
   ```

3. Read the installed BMAD configuration under `<project-root>/_bmad`.
4. Load the installed `bmad-help` skill from the selected host's skill directory.
5. Use `bmad-help` to determine the current lifecycle phase and the next required or optional skill.

## Host mapping

- `codex` and `custom` install through BMAD's shared `.agents/skills` contract.
- `claude` uses `.claude/skills`.
- `kiro` uses `.kiro/skills`.
- `cline` uses `.cline/skills`.
- `copilot` uses `.agents/skills` and `.github/agents`.
- `kilo` uses `.agents/skills`.

## Boundaries

- Project-generated BMAD artifacts belong to the consumer project.
- Installation does not authorize branches, PRs, Jira writes, deployment, approval, Slack messages, or GWC gate transitions.
- Never modify the packaged Power source in place.
