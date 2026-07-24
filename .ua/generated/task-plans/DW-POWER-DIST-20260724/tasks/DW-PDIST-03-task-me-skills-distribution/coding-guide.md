# Coding Guide

## Skill closure

Start with `.kiro/skills/implementation-task-architect/SKILL.md`. Include `references/runbook.md`, `references/evidence-model.md`, `references/task-decomposition.md`, `references/estimation.md`, and `references/output-contract.md` when they exist and are referenced. Verify scripts and schemas by actual path rather than inferred names.

## Configuration

Do not ship the repository's active `.task-architect/config.json` as a ready-to-run consumer config if it contains Task Me repository paths. Generate a neutral example/default with placeholders and schema validation.

## Installation boundary

Installation may copy skill source and write managed host adapters, package metadata, consumer contract, config, and an empty `.task-me` root. It must never invoke Task Me, create `.ua/generated/task-plans`, or call Jira/GitHub.
