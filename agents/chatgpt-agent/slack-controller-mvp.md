# ChatGPT Slack Controller — Human Control Plane MVP

This file is a mandatory additive instruction whenever ChatGPT presents a TaskController run in Slack.

**Slack is the Human Control Plane.** It is the human-facing operational surface, not the Executor progress transport, canonical run state, or audit store.

## Mandatory load order

Read:

1. root `AGENTS.md` and applicable workspace/project instructions;
2. active Power instructions when a Power is selected;
3. `agents/shared/taskcontroller-a2a-protocol.md`;
4. this file;
5. current Slack connector + `Slack Communication Policy` + `Governance Behavior`.

## RootCard

Maintain one concise RootCard per run and update it in place.

Keep visible when available:

- human owner/watcher;
- human-readable current gate/journey when GWC is active;
- Controller and Executor identity;
- actual Executor model;
- token usage if exposed, otherwise `N/A`;
- cost only as `FREE | metered | unknown`;
- active subtask/progress;
- branch / PR / exact HEAD / CI;
- risk/blocker;
- Now / Next;
- last material update;
- Controller health: `ACTIVE | DISCONNECTED | RECOVERED | BLOCKED`.

Contextual human actions:

- `PAUSE` — stop before next meaningful action boundary;
- `STOP` — no new mutation starts;
- `APPROVE` — only when exact human authority exists;
- `MERGE` — only when authority permits and exact PR/head is bound.

Button intent is not authority by itself.

## Semantic timeline

Slack thread replies are a **semantic timeline** only. Emit human-visible updates for material events such as:

- RUN_STARTED;
- SUBTASK_STARTED;
- MILESTONE_REACHED;
- REVIEW_REQUIRED;
- CORRECTION_REQUIRED;
- BLOCKED;
- AUTHORITY_REQUIRED;
- CONTROLLER_RECOVERED;
- TERMINAL.

Do not use Slack thread replies as the Executor progress transport.

Do not mirror:

- A2A ACKs;
- mailbox sequence changes;
- polling heartbeats;
- individual file/tool operations;
- raw tests/CI output;
- recovered transient retries;
- low-level successful operations without semantic consequence.

## Monitoring

Executor progress is observed through the current Agent interaction binding (GitHub reference mailbox in the pilot), not by replaying Slack.

```text
sleep 60s in-session when waiting
→ read mailbox state newer than mailbox cursor
→ validate contract / refs / evidence
→ audit semantic consequence when configured
→ update RootCard / semantic timeline only if material
```

Slack may also be read for human PAUSE/STOP/APPROVE/MERGE input. Human control input and Executor progress transport are separate concerns.

No scheduler/reminder/detached automation replaces the active observation loop.

## INTERCEPT

INTERCEPT only for:

- scope drift;
- authority drift;
- plan drift;
- evidence conflict / base drift;
- material finding that invalidates the next contracted action.

Do not intercept ordinary tool choice, successful retry, normal implementation progress, expected test runtime, or low-level work inside the bounded subtask.

## Recovery

A fresh Controller recovers from canonical task/run identity, current mailbox envelopes/cursors, referenced PR/SHA/CI/artifacts, audit ledger/checkpoint when configured, and the existing Slack RootCard binding.

Full Slack thread replay and previous GPT conversation history are not required recovery inputs.

## MVP boundary

Keep the pilot slim: one Controller, one main Executor, one GitHub mailbox comment per actor, one Slack RootCard/thread for humans, 3–5 contracted subtasks, incremental mailbox observation, semantic Slack projection and bounded intercepts.

Do not add Kafka/MSK/NATS infrastructure, multi-executor scheduling, or other Full-E2E machinery until the pilot demonstrates a concrete need.
