# Agent Instruction Index

This directory contains DW-SuperApps agent overlays. Root `AGENTS.md`, workspace/project instructions, installed Power instructions, and exact repository state remain authoritative.

## TaskController A2A — active interaction path

Any explicit TaskController activation uses the reference-based A2A interaction path. The mandatory composition is:

1. root `AGENTS.md` + applicable workspace/project/Power instructions;
2. `controllers/taskcontroller.yaml`;
3. `agents/chatgpt-agent/agent-instructions.md` for ChatGPT Controller;
4. `agents/shared/taskcontroller-a2a-protocol.md`;
5. `agents/shared/taskcontroller-human-plane-policy.md` when Slack is used as the Human Control Plane;
6. `agents/chatgpt-agent/slack-controller-mvp.md` for ChatGPT's Slack Human Plane transport overlay;
7. `agents/hermes/agent-instructions.md` when Hermes is the Executor.

TaskController boot must materialize/recover the Controller mailbox, Executor mailbox and continuation checkpoint and exact-read the Controller mailbox before first Executor dispatch. Missing mailbox boot is fail-closed; Slack is not a machine-transport fallback.

The active machine path is:

```text
Controller mailbox
→ pointer-only wake-up when required
→ Executor consumes newer Controller seq
→ bounded execution
→ Executor updates its own mailbox comment in place
→ Controller polls exact Executor mailbox/cursor
→ semantic Human Plane projection to Slack
```

Slack is the Human Control Plane only. Tool chatter, command payloads, normal Executor progress, continuation state and recovery state do not belong in Slack.

No Slack-hosted policy document, project-local policy copy, or Power-local policy copy is part of TaskController activation. The canonical Slack/Human Plane semantics are owned entirely by DW-SuperApps through `controllers/taskcontroller.yaml`, `agents/shared/taskcontroller-human-plane-policy.md`, and the selected host transport overlay.

## Legacy Slack Controller–Executor MVP

`agents/shared/slack-controller-executor-protocol.md` is retained only for historical/explicit legacy compatibility. It is NOT part of the active `dw.taskcontroller.a2a/v1` load chain and MUST NOT be loaded as a competing machine transport when TaskController A2A is active.

## Power activation

TaskController activation does not activate any Power. A project/Power instruction set is loaded only when the controlled task explicitly selects or requires that Power.
