# TaskController Reference-Based Agent Interaction Protocol — A2A Pilot

Status: active pilot contract for Controller↔Executor interaction.

## Purpose

This protocol defines **Agent interaction semantics**, independent of transport. The first pilot binding is a GitHub reference mailbox because ChatGPT and heterogeneous Executors can already exchange durable GitHub references without introducing new infrastructure.

**Slack is not the Executor progress transport.** Slack is the Human Control Plane and receives only semantic human projections.

## Core invariant

```text
Controller reasoning / decisions
        ↓
TaskController A2AEnvelope
        ↓
Communication binding
        ↓
Executor
        ↓
A2AEnvelope + artifact/context refs
        ↓
Controller review
        ↓
Audit ledger → Human semantic projection → Slack
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
- the envelope never creates approval/merge/deploy authority by itself.

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

Slack is not audit storage.

## Controller contract

Controller owns:

- decomposition and bounded execution plan;
- selected-option contract;
- milestone/report boundaries;
- expected evidence;
- `CONTINUE | WAIT_CONTROLLER | TERMINAL` behavior;
- review and bounded `INTERCEPT`;
- mailbox cursor and human projection state.

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

Tool chatter, individual file reads/edits, raw test output, repeated CI polling and recovered transient retries remain silent.

## Recovery

A fresh Controller session recovers from:

1. canonical repository/task/run identity;
2. latest Controller and Executor mailbox envelopes;
3. per-actor cursor / last-seen sequence;
4. active contract/subtask;
5. exact referenced PR/SHA/CI/artifact evidence;
6. audit ledger/checkpoint when configured;
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

HEALTH/no-op/polling events may remain invisible unless they materially affect the human decision.

## Authority

Human approval/merge/deploy authority comes from the active repository/project authority model. GitHub mailbox state, Executor completion, Slack buttons or previous messages do not create authority by themselves.
