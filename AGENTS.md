# DW SuperApps Agent Routing

This repository is an orchestration workspace for multiple AI hosts, reusable Powers, model providers, and product systems.

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

Supported hosts include Kiro, Codex, GitHub Copilot, Cline, Kilo Code, Claude Code, and generic/custom agents. Host-specific folders expose only thin discovery adapters. They must not duplicate Power logic, schemas, or runtime data.

`bionics`, `biotic`, and `ollama` are accepted aliases for the generic `custom` host. Ollama itself is a model provider, not a host; its OpenAI-compatible endpoint is registered separately.

## Model providers

Local Ollama compatibility uses:

- Base URL: `http://localhost:11434/v1`
- API key placeholder: `ollama`
- Model override: `OLLAMA_MODEL`

Provider configuration must not contain real secrets.

## Cross-repository work

A change affecting multiple systems must identify every impacted repository explicitly. Do not assume one repository approval, branch, task, or validation result applies to another repository.

## Slack Notification Behavior

Slack is an optional notification channel for execution visibility.

Slack is used for:

- Gate transition updates
- Blocker notifications
- Important milestone notifications
- Human visibility of agent execution

Slack is NOT:

- The governance source of truth
- The task state store
- The approval authority

## Gate Event Rule

After important execution events, the agent should:

1. Confirm or update the current task state.
2. Record evidence and audit information.
3. Send Slack notification when Slack capability is available.
4. Continue execution if Slack is unavailable.

Important events include:

- Task started
- Gate started
- Gate completed
- Gate blocked
- PR created
- CI validation completed
- Approval requested
- Human override
- Task completed

## Slack Failure Handling

Slack availability must never block work.

If Slack is unavailable:

- Continue the workflow.
- Record or mention that notification was skipped.
- Keep the execution result unchanged.
