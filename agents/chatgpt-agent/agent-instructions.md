# ChatGPT Agent Instructions — DW-SuperApps

These instructions are an additive overlay on root `AGENTS.md` and applicable workspace/project/Power instructions.

## TaskController activation guard

When the current user message explicitly contains `TaskController`, `task controller`, or `/dw-taskcontroller`, activation is mandatory **before planning, delegating, posting to Slack, or claiming the controller is booted**.

Resolve from current repository state, not memory:

1. verify current DW-SuperApps default branch / exact `main` SHA when online;
2. read root `AGENTS.md`;
3. read `workspace.yaml` and confirm enabled controller `taskcontroller`;
4. read `controllers/taskcontroller.yaml`;
5. read `agents/README.md`;
6. load the host/transport/executor entrypoints required by that registry.

For ChatGPT + Slack, this necessarily includes:

- `agents/shared/slack-controller-executor-protocol.md`
- `agents/chatgpt-agent/slack-controller-mvp.md`
- current Slack connector
- `Slack Communication Policy`
- `Governance Behavior`

For Hermes execution, also require `agents/hermes/agent-instructions.md`.

Do not substitute conversation memory, prior summaries, old Slack messages, a previous session's activation, or the existence of TaskController Python modules for this load chain. If any mandatory entrypoint is unavailable, report activation `BLOCKED` instead of fabricating a RootCard/contract.

The current MVP uses `taskcontroller/mvp/activation.py` for deterministic explicit-mention routing and `taskcontroller/mvp/protocol_bridge.py` for verdict translation. Full-E2E runtime modules remain deferred unless current repository policy separately activates them.

## Default role

ChatGPT may act as analyst, planner, reviewer, orchestrator, or Controller according to the active task. Repository/project authority remains defined by root and active project/Power instructions.

## Slack Controller mode

When ChatGPT controls an Executor through Slack, it MUST load and follow:

1. `agents/shared/slack-controller-executor-protocol.md`
2. `agents/chatgpt-agent/slack-controller-mvp.md`

The Slack Controller overlay is mandatory for that run, not optional reference material.

The Controller owns task decomposition, selected-plan contracting, milestone/report timing, WAIT points, RootCard state, report review, incremental polling, and bounded INTERCEPT decisions.

The Controller must not delegate an ambiguous task and allow the Executor to invent its own plan or reporting cadence.

## GWC-active tasks

When GWC is active, the Controller must not delegate write-capable execution before the required G2 authority exists. It compiles the Executor-facing contract from G0 context, the G1 selected option only, exact G2 authority, and exact current repository evidence.

Rejected alternatives, brainstorming noise, and superseded options must not be forwarded to the Executor.

GWC is loaded only when the controlled task/project requires it; activating TaskController alone does not implicitly activate GWC.

## Monitoring invariant

During an active Slack Controller run:

```text
sleep 60s
→ read only new thread replies after last_seen_ts
→ validate reports against the contracted milestone
→ continue | review | intercept | terminal
```

Polling is silent and remains in-session. Do not replace it with a scheduler, reminder, or detached automation.

Use `WAIT_CONTROLLER` only at high-value review or authority boundaries so control does not create unnecessary latency.

## Communication invariant

RootCard is the concise human snapshot. Slack thread replies are the structured execution journal. Thinking, raw tool output, tool chatter, repetitive polling, and recovered transient retries stay silent.

Executor reports must follow the report requirements and subtask boundaries defined by the Controller contract.