# Agent Instruction Index

This directory contains DW-SuperApps agent overlays. Root `AGENTS.md`, `workspace.yaml`, controller registries, project instructions, installed Power instructions, exact repository state, and TaskController audit evidence remain authoritative.

## TaskController explicit activation

`TaskController` is a first-class **workspace controller**, not a Power.

Any explicit user mention of one of these aliases activates it:

- `TaskController`
- `task controller`
- `/dw-taskcontroller`

On activation, do not rely on conversation memory, a prior "booted" claim, or Slack history. Resolve the current repository and load the canonical chain declared by `controllers/taskcontroller.yaml`.

The base load order starts with:

1. root `AGENTS.md`
2. `workspace.yaml`
3. `controllers/taskcontroller.yaml`
4. this index
5. current host overlay
6. `agents/shared/taskcontroller-a2a-protocol.md`
7. human-plane/executor overlays required by the registry

If a required entrypoint is missing or cannot be read, activation is `BLOCKED`; do not synthesize a controller contract from memory.

## Agent interaction pilot

Current Agent interaction is **reference-based A2A**:

- semantic protocol: `dw.taskcontroller.a2a/v1`;
- pilot binding: GitHub reference mailbox;
- one actor = one mutable mailbox comment;
- context/evidence by exact reference;
- Controller observes monotonically increasing per-actor mailbox sequence/cursor;
- TaskController audit ledger records semantic events when configured;
- binding IDs never become canonical TaskController IDs.

The same protocol may later bind to A2A HTTP, local IPC, NATS, Kafka/MSK, or another transport without changing Controller/Executor semantics.

## Slack Human Control Plane

When ChatGPT presents a controlled run in Slack, the mandatory additive chain includes:

1. `agents/chatgpt-agent/agent-instructions.md`
2. `agents/shared/taskcontroller-a2a-protocol.md`
3. `agents/chatgpt-agent/slack-controller-mvp.md`
4. current Slack connector + `Slack Communication Policy` + `Governance Behavior`

For Hermes Executor, also load `agents/hermes/agent-instructions.md`.

Slack is the Human Control Plane: one RootCard plus a compact semantic timeline. Slack is not the Executor progress transport and not canonical run/audit state. Machine polling, ACKs, mailbox sequence churn, raw CI polling, file/tool chatter and retry noise stay out of Slack.

## Controller / Executor boundary

The Controller owns decomposition, selected-plan contracting, report timing, expected evidence, WAIT points, RootCard state, mailbox observation, review and bounded INTERCEPT decisions.

The Executor follows the bounded contract, verifies exact repository/base/head assumptions in its own environment, updates its mailbox at contracted milestones/material exceptions, and does not invent a different plan or authority.

## Recovery

A fresh Controller recovers from current repository/task/run identity, mailbox envelopes/cursors, referenced PR/SHA/CI/artifacts, audit ledger/checkpoint when configured, and the Slack RootCard binding. Conversation history and full Slack thread replay are not recovery requirements.

## GWC boundary

TaskController activation does not automatically activate GWC. Load GWC only when the controlled task/project requires that governance model.
