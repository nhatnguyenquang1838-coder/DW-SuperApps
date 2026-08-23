# ChatGPT Agent Instructions — DW-SuperApps

These instructions are an additive overlay on root `AGENTS.md` and applicable workspace/project/Power instructions.

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