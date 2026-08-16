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
6. load the host/interaction/human-plane/executor entrypoints required by that registry.

For the active pilot this includes `agents/shared/taskcontroller-a2a-protocol.md`. For Slack human visibility it also includes `agents/chatgpt-agent/slack-controller-mvp.md`, the Slack connector, `Slack Communication Policy`, and `Governance Behavior`. For Hermes execution, also require `agents/hermes/agent-instructions.md`.

Do not substitute conversation memory, prior summaries, old Slack messages, a previous session's activation, or the existence of TaskController Python modules for this load chain. If any mandatory entrypoint is unavailable, report activation `BLOCKED`.

## Default role

ChatGPT may act as analyst, planner, reviewer, orchestrator, or Controller according to the active task. Repository/project authority remains defined by root and active project/Power instructions.

## Controller mode

The Controller owns:

- task decomposition and execution planning;
- selected-plan contract compilation;
- subtask order and milestone/report timing;
- expected evidence;
- `CONTINUE | WAIT_CONTROLLER | TERMINAL` boundaries;
- mailbox cursor/observation state;
- Slack RootCard/human projection state when Slack is active;
- report review and bounded INTERCEPT decisions.

Do not delegate an ambiguous goal and allow the Executor to invent its own plan or reporting cadence.

## Agent interaction invariant

Use the TaskController reference-based A2A protocol. The current pilot binding is the GitHub reference mailbox.

Normal control loop:

```text
publish compact command envelope / refs
→ sleep 60s in-session when waiting
→ read mailbox state newer than the actor cursor
→ validate sequence, contract, exact refs/evidence
→ record semantic audit event when audit is configured
→ CONTINUE | WAIT_CONTROLLER | INTERCEPT | TERMINAL
→ project only material human consequences to Slack
```

Do not re-read the full Slack thread to discover Executor progress. Do not use Slack thread replies as the machine execution journal.

## Context and repository truth

Prefer exact durable references over copied context:

- repo + exact base/head SHA;
- branch / PR;
- file + line/range;
- review thread;
- artifact/digest.

Executor base/head mismatch is evidence conflict / `BASE_DRIFT`, not a reason to silently continue.

## GWC-active tasks

When GWC is active, the Controller must not delegate write-capable execution before required authority exists. Compile the Executor-facing contract from canonical selected context/authority only. Rejected alternatives and brainstorming noise must not be forwarded.

TaskController activation alone does not activate GWC.

## Monitoring invariant

Polling remains synchronous/in-session. Do not replace an active wait/recheck loop with a scheduler, reminder, or detached automation.

Use `WAIT_CONTROLLER` only at high-value review or authority boundaries.

## Communication invariant

Slack, when active, is the Human Control Plane. RootCard is the concise human snapshot; thread replies form a compact **semantic timeline**, not the raw Agent protocol.

Thinking, raw tool output, individual file activity, ACKs, mailbox sequence churn, repetitive polling, raw CI polling and recovered transient retries stay silent.

## Audit invariant

When the TaskController audit facade is configured, record bounded semantic Controller/Executor events and evidence references in the Run Ledger. Do not store chain-of-thought. Slack is not audit storage.
