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

## Session boot — A2A and mailboxes first

TaskController activation MUST boot the A2A interaction state before the first Executor dispatch. Boot is not complete merely because the instruction files were read or a Slack RootCard exists.

Required boot state:

- exactly one Controller mailbox reference for the run;
- exactly one Executor mailbox reference for the run;
- Controller and Executor mailbox cursors/expected sequence;
- an ACTIVE `dw.taskcontroller.continuation/v1` checkpoint bound to the current exact head and both mailbox refs;
- the Controller mailbox updated in place with that same checkpoint and exact-read back successfully.

Required order:

```text
resolve current repository/run identity
→ materialize or recover Controller mailbox
→ materialize or recover Executor mailbox
→ persist continuation checkpoint
→ write Controller mailbox with same checkpoint
→ exact-readback Controller mailbox/seq
→ send pointer-only wake-up when the provider requires it
→ poll exact Executor mailbox comment only
```

If any required mailbox/checkpoint/readback cannot be established, fail closed with `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED`. Do not copy the command into Slack, use Slack thread progress as substitute state, or recover by replaying Slack/GPT history.

Activating TaskController does not activate GWC. GWC is loaded only when the current controlled task requires its governance model.

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

## High-integrity admission boundary

The v1 mutable-comment lane remains a compatibility lane. A controlled task that requires external governance/gate semantics, human effect approval, or digest-bound execution identity MUST enter the high-integrity lane before Controller dispatch/review.

High-integrity admission requires:

- protocol `dw.taskcontroller.mailbox/v2`;
- `taskcontroller/controlplane/controller_admission.py` PASS;
- exact mailbox reference/event cursor reads only;
- canonical typed envelope/artifact digest for semantic identity;
- descriptor-bound schema resolution;
- observed or canonically recomputed digests only;
- current verified gate/boundary as the input to preapproval;
- typed approval-request + verified approval-command digest for human approval presentation.

The following are transport/debug evidence only and MUST NOT become semantic authority:

- raw mutable GitHub comment-body SHA;
- issue-wide comment history;
- a Controller-predicted digest/hash;
- a guessed legacy schema path;
- a target-gate state synthesized before the target gate's authority artifact exists.

If a host cannot satisfy the high-integrity admission contract, it must stop with a Controller admission blocker. It must not downgrade to v1 to continue an authority-sensitive run.

This boundary does not grant effect, merge, deploy, release, migration, secret, or production authority.

## High-integrity GitHub mailbox/v2 binding

When the high-integrity lane uses the GitHub binding, the canonical remote adapter is `taskcontroller.interaction.github_mailbox_v2.GitHubMailboxRepository`.

The mailbox reference has the form:

`github://<owner>/<repo>/issues/<issue>#<actor-mailbox>`

Transport rules:

- each accepted mailbox event is appended as a new immutable GitHub issue comment using `dw.taskcontroller.github-mailbox-record/v1`;
- each durable actor-cursor acknowledgement is also appended as a new immutable GitHub issue comment;
- unrelated issue comments are not mailbox records and are ignored;
- a tagged malformed mailbox record fails closed;
- exact readback validates canonical envelope/event/cursor identity, not full comment-body SHA;
- the current topology requires one writer per actor mailbox; the adapter does not claim cross-process multi-writer atomic CAS;
- Controller and Executor use separate actor mailbox refs when both can write concurrently;
- high-integrity runs MUST NOT update one mutable actor comment in place.

This transport binding does not grant execution authority. Gate/effect authority remains separately validated.

For high-integrity remote recovery, persist the bounded `dw.taskcontroller.continuation/v1` manifest through `taskcontroller.interaction.github_continuation_store.GitHubContinuationStore` before the first mailbox/v2 dispatch and before every later Controller dispatch checkpoint. Continuation records are append-only GitHub issue comments using `dw.taskcontroller.github-continuation-record/v1`, exact-read back after append, and filtered by exact `run_id + manifest_kind`. The same Controller writer owns continuation updates for the run.

A high-integrity mailbox event without a durable remote continuation checkpoint is invalid boot state and MUST NOT be emitted.

## Controller execution-contract modes

Mailbox/v2 requests may declare one Controller contract mode:

- `PLAN`: source recovery, research, design, decomposition, validation; no implementation effects.
- `TRANSPORT_REPAIR`: mailbox/protocol/continuation repair only.
- `EXECUTE`: bounded real engineering work after applicable execution authority is validated.

`EXECUTE` is outcome-oriented. It must include a real writable scope, at least one engineering mutation action, ordered work packages, continue-until conditions, and hard stop conditions. A read/validate/report-only package is not a valid EXECUTE contract.

Within an EXECUTE boundary, implementation details belong to the Executor. Normal RED/GREEN/test/fix/refactor cycles are not separate mailbox authority boundaries and must not create repetitive WAIT_CONTROLLER turns.

One bounded execution package may include branch/worktree creation, approved file edits, tests, staging, commit, push, and Draft PR when explicitly authorized. Merge, Ready-for-Review when separately governed, deploy, production/data/secret/migration/destructive actions remain separate authority.

The transport does not grant authority. `taskcontroller/controlplane/execution_contracting.py` validates the declared mode before dispatch persistence and must return `authority_granted=false`.

### Controller-owned HITL and anti-stuck invariant

For high-integrity mailbox/v2 runs, the authority topology is always:

```text
Human/User <-> Controller <-> Executor
```

The Executor MUST NOT address an approval request to the Human/User, emit `WAIT_USER_*` / `WAIT_HUMAN_*`, mint an approval command/token, or create a direct Human wait loop. When execution reaches a boundary, the Executor reports it to the Controller. The Controller alone resolves whether the next action is automatic, delegated, or Human HITL and materializes the exact actionable request.

Executor blocker reports are limited to four canonical classes:

- `AUTHORITY_BOUNDARY`;
- `SCOPE_EXPANSION`;
- `MATERIAL_PLAN_INVALIDATION`;
- `EXTERNAL_DEPENDENCY_BLOCKED`.

Source/base/identity drift is reported as material-plan invalidation with an exact subreason/evidence reference; a required write outside scope is scope expansion; a later separately governed gate is an authority boundary.

`execution_progress` is a first-class Controller resume input. RUNNING progress is observational and MUST NOT require a release command. SUCCEEDED progress may close the delegated mission at its declared ceiling. BLOCKED / NEEDS_CLARIFICATION progress requires one canonical blocker class and Controller ownership of the next decision. Atomic missions with `max_children=0` may emit a canonical terminal result with empty child provenance; child evidence MUST NOT be fabricated.

A mission-level `EXECUTE` contract remains active across its internal work packages until `continue_until` is satisfied or one canonical blocker occurs. Work-package completion is not an authority boundary by itself.

HOLD is typed:

- `EFFECT_HOLD`: blocks only explicitly named effects and keeps the Controller control loop running for allowed read/plan/recovery/remediation work;
- `RUN_HOLD`: stops new run actions until a fresh release.

An untyped/generic HOLD is invalid. An effect authority wait MUST NOT strand bounded runnable read-only work.

A Human-required state is invalid unless the Controller has materialized an actionable Human request. A delegated-authority state is invalid unless a delegate dispatch receipt exists. If no resolver is actually routed, fail closed with `AUTHORITY_REQUEST_UNROUTED`; do not persist a silent wait.

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
