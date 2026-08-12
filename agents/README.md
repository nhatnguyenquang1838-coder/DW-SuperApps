# Agent Instruction Index

This directory contains DW-SuperApps agent overlays. Root `AGENTS.md`, workspace/project instructions, installed Power instructions, and exact repository state remain authoritative.

## Slack Controller–Executor MVP

When a task uses the Slack Controller–Executor pilot, load:

1. `agents/shared/slack-controller-executor-protocol.md`
2. Role overlay:
   - GPT Controller: `agents/chatgpt-agent/slack-controller-mvp.md`
   - Hermes Executor: `agents/hermes/agent-instructions.md`
3. If GWC is active for the task, load the applicable GWC/coding-agent lifecycle before execution.

The MVP is intentionally slim: one Controller, one Executor, one RootCard/thread, 3–5 subtasks, contracted milestone reports, in-session 60-second polling, and bounded intercepts. Full E2E sequencing/replay/recovery/multi-executor logic is deferred until pilot acceptance.
