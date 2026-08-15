# Agent Instruction Index

This directory contains DW-SuperApps agent overlays. Root `AGENTS.md`, `workspace.yaml`, controller registries, project instructions, installed Power instructions, and exact repository state remain authoritative.

## TaskController explicit activation

`TaskController` is a first-class **workspace controller**, not a Power.

Any explicit user mention of one of these aliases activates it:

- `TaskController`
- `task controller`
- `/dw-taskcontroller`

On activation, do not rely on conversation memory, a prior "booted" claim, or Slack history. Resolve the current repository and load the canonical chain declared by `controllers/taskcontroller.yaml`. Hosts may use `taskcontroller.mvp.resolve_taskcontroller_activation(...)` as the deterministic resolver.

The base load order starts with:

1. root `AGENTS.md`
2. `workspace.yaml`
3. `controllers/taskcontroller.yaml`
4. this index
5. the current host overlay
6. transport/executor overlays required by the registry

If a required entrypoint is missing or cannot be read, activation is `BLOCKED`; do not synthesize a controller contract from memory.

## Slack Controller–Executor MVP

When ChatGPT is acting as Controller for a Slack-mediated Executor run, the following additive instruction chain is **mandatory**:

1. root `AGENTS.md` + `workspace.yaml` + `controllers/taskcontroller.yaml` + applicable project/Power instructions
2. `agents/chatgpt-agent/agent-instructions.md`
3. `agents/shared/slack-controller-executor-protocol.md`
4. `agents/chatgpt-agent/slack-controller-mvp.md`

For Hermes Executor, load:

1. applicable project/Power and normal coding-agent/GWC lifecycle when GWC is active
2. `agents/shared/slack-controller-executor-protocol.md`
3. `agents/hermes/agent-instructions.md`

For Slack transport, also load the current Slack connector plus the `Slack Communication Policy` and `Governance Behavior` canvases before posting.

The MVP is intentionally slim: one Controller, one Executor, one RootCard/thread, 3–5 contracted subtasks, milestone-based reporting, in-session 60-second incremental polling, explicit `CONTINUE | WAIT_CONTROLLER | TERMINAL` behavior, and bounded intercepts.

The GPT Controller owns decomposition, report timing, expected milestone evidence, WAIT points, RootCard state, incremental observation, review and intercept decisions. The Executor must not invent a different plan or arbitrary reporting cadence.

Full E2E sequencing/replay/recovery/multi-executor logic is deferred until pilot acceptance. In particular, the existence of `SlackTaskControllerPack` or other Full-E2E library modules does not mean they are active in the current MVP.