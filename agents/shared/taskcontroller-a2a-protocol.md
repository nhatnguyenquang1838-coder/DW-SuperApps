# TaskController Reference-Based Agent Interaction Protocol — A2A Pilot

Status: active pilot contract for Controller↔Executor interaction.

## Purpose

This protocol defines **Agent interaction semantics**, independent of transport. The first pilot binding is a GitHub reference mailbox because ChatGPT and heterogeneous Executors can already exchange durable GitHub references without introducing new infrastructure.

**Slack is not the Executor progress transport.** Slack is the Human Control Plane and receives only semantic human projections. When an idle Executor cannot poll/push-subscribe to its mailbox, Slack may also carry a separate **pointer-only wake-up notification**.

## Core invariant

```text
Controller reasoning / decisions
        ↓
TaskController A2AEnvelope
        ↓
Agent mailbox / communication binding
        ↓
Executor
        ↓
A2AEnvelope + artifact/context refs
        ↓
Controller review
        ↓
Audit ledger → Human semantic projection → Slack
```

An optional notification path sits beside, not inside, the data path:

```text
Controller mailbox seq advances
        ↓
WakeupSignal(run_id, recipient, mailbox_ref, seq)
        ↓
Notification binding (Slack wake-up in pilot)
        ↓
Executor fetches canonical payload from mailbox
```

The communication binding may later be GitHub, A2A HTTP, local IPC, NATS, Kafka/MSK or another provider without changing the semantic contract.

## Pilot mailbox model

For the GitHub pilot:

- one Controller identity per run;
- one main Executor in the first vertical slice;
- **one actor = one mutable mailbox comment**;
- each actor updates its own mailbox comment in place;
- a monotonically increasing `seq` identifies a new mailbox state;
- Controller keeps a per-actor mailbox cursor and ignores/rejects stale or duplicate sequences;
- GitHub comment/PR/thread IDs are binding metadata, never canonical TaskController IDs.

Normal progress does not append a new comment for every event.

## Envelope

Use `dw.taskcontroller.a2a/v1` and the typed `taskcontroller.interaction.A2AEnvelope`.

Required semantics:

```text
run_id
node_id
sender
recipient
seq
kind = COMMAND | REPORT | REVIEW_REQUEST | CORRECTION | TERMINAL | HEALTH
inputs = references
artifact_refs = references
request = compact semantic request when needed
state = bounded machine state
updated_at
```

Rules:

- no chain-of-thought;
- no full Slack/GPT conversation replay;
- no copied repository body when an exact durable reference exists;
- large outputs become artifact refs;
- request is limited to 4096 characters;
- state is limited to 8192 UTF-8 bytes;
- at most 16 input refs and 16 artifact refs per envelope;
- the envelope never creates approval/merge/deploy authority by itself.

## Controller continuation / liveness

A TaskController run is **not** the lifetime of one GPT response.

Before dispatching or waking an Executor, the Controller MUST persist a `dw.taskcontroller.continuation/v1` checkpoint. The checkpoint contains only bounded continuation metadata: run/epoch/phase/next action, Controller/Executor mailbox pointers and cursors, exact head SHA, wake-up binding, and optional Human RootCard ref.

For the GitHub pilot, the same checkpoint is embedded in the Controller mailbox envelope state so a fresh Controller execution can recover it through a durable shared binding. When audit persistence is configured, the checkpoint is also mirrored into the Run Ledger manifest table.

Required pre-dispatch sequence:

```text
persist continuation
→ write Controller mailbox with same checkpoint
→ exact-readback Controller mailbox
→ send provider wake-up
→ poll exact Executor mailbox comment only
```

An `ACTIVE` continuation checkpoint forbids a semantic Controller final/terminal response. The Controller may stop the current host execution only at a genuine human-authority or unrecoverable blocker while leaving the durable run state truthful and recoverable.

While the host execution remains alive, polling is synchronous/in-session at the configured cadence. Polling MUST fetch only the exact Executor mailbox comment referenced by the checkpoint; it MUST NOT repeatedly load the whole GitHub issue, Slack thread, or GPT conversation.

For the current `hermes-cloud` provider, `slack-websocket` is a REQUIRED wake-up binding because Slack WebSocket is Hermes's trigger point. This requirement does not make Slack the command/data bus.

## Wake-up notification

Use `dw.taskcontroller.wakeup/v1` and typed `WakeupSignal` only when an Executor needs an external signal to notice unseen mailbox work.

The signal is **pointer-only**:

```text
run_id
sender
recipient
mailbox_ref
seq
updated_at
```

It MUST NOT carry `request`, `inputs`, `artifact_refs`, `state`, code, context body or command payload. The Executor uses `mailbox_ref` to fetch the canonical A2AEnvelope and validates whether `seq` is newer than its mailbox cursor.

Wake-up delivery is safe to duplicate. Stale/equal sequence does not announce new work. Notification message IDs are transport metadata only.

In the Slack pilot, a wake-up mention is allowed only as `SlackWakeupBinding`; it does not turn Slack into the command/progress bus. After wake-up the Executor reads GitHub and reports to its mailbox. Tool/progress narration on the wake-up channel is forbidden.

## Context contract

Use **context by exact reference**.

For engineering work prefer:

```text
repository + exact base/head SHA
branch / Draft PR
path + line/range
PR review thread for code-specific discussion
artifact ref/digest when available
```

Existing `InputRef(input_id, source_ref, media_type)` is the first context-reference carrier. Do not create a second context schema unless the pilot demonstrates a need.

Before mutation, an Executor verifies the contracted repository/base/head assumptions in its own environment. A material mismatch is `BASE_DRIFT` / evidence conflict and must be surfaced instead of silently continuing.

## Audit trail

When an audit facade is configured, semantic Agent interaction events are recorded to the TaskController Run Ledger before or alongside human projection. The ledger records bounded decision/event metadata and references; it does not store chain-of-thought.

Audit evidence must preserve at minimum:

- run/node identity;
- actor;
- envelope sequence/kind;
- evidence/artifact references;
- mailbox/raw payload reference when available;
- semantic summary only.

The configured Run Ledger also stores the latest continuation manifest. Wake-up delivery may be audited as pointer metadata and delivery outcome; it does not duplicate the canonical command payload. Slack is not audit storage.

## Controller contract

Controller owns:

- decomposition and bounded execution plan;
- selected-option contract;
- milestone/report boundaries;
- expected evidence;
- `CONTINUE | WAIT_CONTROLLER | TERMINAL` behavior;
- review and bounded `INTERCEPT`;
- mailbox cursor and human projection state;
- durable continuation checkpoint and recovery;
- pointer-only wake-up when the selected Executor requires it.

Do not send rejected alternatives, brainstorming noise, superseded options or unrelated context to the Executor.

For the slim pilot, use 3–5 meaningful contracted subtasks unless the active task explicitly requires a different shape.

## Executor reporting

Executor updates its own mailbox at contracted milestones and material exceptions. It must immediately report:

- scope drift;
- authority drift;
- evidence conflict;
- base/head drift;
- blocker/failure;
- material finding invalidating the next contracted action.

Tool chatter, individual file reads/edits, raw test output, repeated CI polling and recovered transient retries remain silent. The same silence rule applies after a wake-up notification.

## Recovery

A fresh Controller execution recovers from:

1. canonical repository/task/run identity;
2. latest Controller mailbox envelope and its continuation checkpoint;
3. latest Executor mailbox envelope and per-actor cursor / last-seen sequence;
4. active contract/subtask;
5. exact referenced PR/SHA/CI/artifact evidence;
6. audit ledger continuation manifest/checkpoint when configured;
7. latest Slack RootCard binding for human continuity.

Conversation history and Slack thread history are not required recovery inputs.

## Human projection

Machine state is compacted before Slack. Normal visible events are bounded to semantic milestones such as:

- RUN_STARTED;
- SUBTASK_STARTED;
- MILESTONE_REACHED;
- REVIEW_REQUIRED;
- CORRECTION_REQUIRED;
- BLOCKED;
- AUTHORITY_REQUIRED;
- CONTROLLER_RECOVERED;
- TERMINAL.

HEALTH/no-op/polling events may remain invisible unless they materially affect the human decision. A wake-up notification is an Executor delivery signal, not a semantic progress event.

## Authority

Human approval/merge/deploy authority comes from the active repository/project authority model. GitHub mailbox state, continuation state, wake-up delivery, Executor completion, Slack buttons or previous messages do not create authority by themselves.
