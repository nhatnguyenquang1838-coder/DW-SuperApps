# DW SuperApps Agent Routing

This repository is an orchestration workspace for multiple AI hosts, reusable Powers, and product systems.

## Discovery

1. Read `workspace.yaml`.
2. Resolve the target system under `systems/`.
3. Load only the Powers enabled for that system.
4. Treat each Power repository as independently versioned source.
5. Keep generated and runtime data inside the owning system repository.

## Power roles

- `powers/gwc`: governance and delivery workflows.
- `powers/ua`: semantic/codebase knowledge generation and query.
- `powers/task-me`: impact analysis and implementation task planning.

## Host neutrality

Kiro and Codex are hosts. Host-specific folders may expose discovery metadata or thin adapters, but must not duplicate Power logic, schemas, or runtime data.

## Cross-repository work

A change affecting multiple systems must identify every impacted repository explicitly. Do not assume one repository approval, branch, task, or validation result applies to another repository.
