# Codex Workspace Adapter

Codex should begin at the workspace root, read `AGENTS.md` and `workspace.yaml`, then enter the target system directory before implementation.

For Rental Home:

1. Treat `systems/rental-home` as the product repository and source of project-local instructions.
2. Reuse Power instructions, schemas, and scripts from `powers/` without copying them into `.codex`.
3. Write UA, Task Me, and GWC runtime artifacts only inside the Rental Home repository.
4. Keep commits and pull requests scoped to the repository being changed.

This directory is a thin host adapter. Canonical Power behavior belongs in each Power repository.
