# Kiro Workspace Adapter

Use `workspace.yaml` as the system and Power registry.

For Rental Home:

1. Read `systems/rental-home/AGENTS.md` and project-local Kiro steering.
2. Use `powers/ua` for semantic analysis while writing generated knowledge to `systems/rental-home/.ua/`.
3. Use `powers/task-me` for impact analysis and implementation planning while writing outputs to `systems/rental-home/.task-me/`.
4. Use `powers/gwc` only when governance or delivery control is explicitly activated for the task.

Do not store generated system knowledge inside `powers/`.
