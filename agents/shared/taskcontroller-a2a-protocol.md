# TaskController Reference-Based Agent Interaction Protocol — A2A Pilot

Status: active canonical mailbox/v2 contract for Controller↔Executor interaction. A2A/v1 is compatibility-only.

## Purpose

This protocol defines **Agent interaction semantics**, independent of transport. The canonical GitHub binding is append-only `dw.taskcontroller.mailbox/v2`; the older mutable-comment `dw.taskcontroller.a2a/v1` binding is retained only for explicit compatibility runs.

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

## Session boot — Controller-owned gates before Executor dispatch

The canonical mailbox/v2 boot requirement applies **before the first Executor dispatch**. TaskController **source/Controller activation** and **Executor dispatch readiness** are distinct states. A fresh Controller may validate its native run context, assign itself understanding/planning/recovery actions and persist the native gate receipts without a live Executor session, Executor acknowledgement, lease, notification adapter, or a mailbox event. Do not issue a placeholder execution request to boot Controller-only work. Native gate/receipt checks and `RUN_HOLD` still govern.

For a real **Controller → Executor** dispatch, the prerequisites are:

- exactly one Controller mailbox/v2 reference and one separate Executor mailbox/v2 reference for the new run (fresh refs may be empty beforehand);
- bound recipient/Executor actor identity and a qualified event-driven delivery route;
- the required exact source, contract/scope/authority checks;
- a durable `dw.taskcontroller.continuation/v1` checkpoint bound to the current exact head, the two mailbox refs and cursor/expected sequences;
- a canonical typed Controller event and producer cursor, plus exact-readback of event, cursor and continuation, **before** notification.

Required order at the **first dispatch**, not before Controller-native gate work:

```text
resolve current repository/run identity + native gate owner
→ if CONTROLLER-owned: perform native action and validate native receipt; do not dispatch
→ if EXECUTOR-owned: validate actor/route/scope/authority and prepare dispatch
→ bind the Controller and Executor mailbox/v2 refs
→ native materialize_controller_transition (persist continuation first)
→ append-only canonical Controller event + producer cursor; exact-readback all three
→ signal pointer-only notification to the qualified Executor adapter
→ Executor performs its own PRECHECK on received command
→ Controller resumes only on a newer valid Executor event, without polling
```

A missing Executor session or notification route is a **dispatch blocker only**; it MUST NOT block an otherwise legal Controller-owned native gate. If a required mailbox/continuation/readback is missing **at dispatch**, fail closed with `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED`. Never update the canonical v2 actor mailbox comment in place; never hand-author records, poll periodically, use Slack as machine fallback, or replay old session events.

Activating TaskController does not activate GWC. GWC is loaded only when the current controlled task requires its governance model.

## Legacy v1 compatibility mailbox model

This section applies only when activation explicitly opts into A2A/v1 compatibility. It is not the default TaskController runtime.

For legacy v1 compatibility:

- one Controller identity per run;
- one main Executor in the first vertical slice;
- **one actor = one mutable mailbox comment**;
- each actor updates its own mailbox comment in place;
- a monotonically increasing `seq` identifies a new mailbox state;
- Controller keeps a per-actor mailbox cursor and ignores/rejects stale or duplicate sequences;
- GitHub comment/PR/thread IDs are binding metadata, never canonical TaskController IDs.

Normal progress does not append a new comment for every event.

## Legacy v1 envelope

Only an explicit compatibility run uses `dw.taskcontroller.a2a/v1` and the typed `taskcontroller.interaction.A2AEnvelope`. Canonical runs use the mailbox/v2 envelope/event contract below.

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

For the canonical GitHub mailbox/v2 lane, the checkpoint is stored as a separate **append-only** `dw.taskcontroller.continuation/v1` manifest through `GitHubContinuationStore`, then referenced by checkpoint identity from the deterministic Controller envelope. It is not a mutable Controller mailbox comment. When audit persistence is configured, the checkpoint is also mirrored into the Run Ledger manifest table.

Required pre-dispatch sequence:

```text
persist continuation
→ write Controller mailbox with same checkpoint
→ exact-readback Controller mailbox
→ publish provider mailbox-event notification
→ remain at AWAIT_EXECUTOR_EVENT
→ on a newer Executor event, exact-read that event once and resume
```

An `ACTIVE` continuation checkpoint forbids a semantic Controller final/terminal response. The Controller may stop the current host execution only at a genuine human-authority or unrecoverable blocker while leaving the durable run state truthful and recoverable.

Canonical mailbox/v2 execution is event-driven. The Controller MUST NOT run a periodic mailbox polling cadence. A `WAIT_EXECUTOR` continuation uses `AWAIT_EXECUTOR_EVENT`; the Controller resumes only after a provider/event adapter reports a newer Executor mailbox event, then exact-reads that event once.

For the current `hermes-cloud` binding, machine notification is a mailbox event. Slack WebSocket is not a canonical Executor wake-up path and MUST NOT be used as machine notification for event-driven runs.

## Wake-up notification

Use `dw.taskcontroller.wakeup/v1` and typed `WakeupSignal` only as a transport-neutral pointer when a provider event adapter needs an external signal to notice unseen mailbox work. Canonical event-driven runs do not use periodic polling.

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

Slack MUST NOT be used as the machine wake-up path for canonical event-driven mailbox/v2 execution. Human-plane projection remains separate from Executor notification.

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

The v1 mutable-comment lane is demoted to explicit compatibility only. New TaskController activations default to mailbox/v2. A controlled task MUST NOT silently select or fall back to v1; compatibility requires an explicit activation choice.

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

The canonical remote adapter is `taskcontroller.interaction.github_mailbox_v2.GitHubMailboxRepository`, composed by `taskcontroller.runtime.high_integrity_session.materialize_controller_transition`. Controller hosts MUST NOT render or post mailbox event/cursor/continuation JSON directly.

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

The materializer owns `record_type`, event/cursor sequence values, previous-event digests, event/envelope digests, and continuation-chain sequencing. Callers supply only the bounded semantic transition. Raw secret/token/credential values are not valid mailbox payload state; durable references/digests must be used instead.

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



## Read-only Analyzer Child Run invariants (SCRUM-808)

These invariants prevent read-only Analyzer Child Run deadlock behind effect authority:

1. **READ_ONLY_ANALYSIS Child Run ≠ Repository G2 effect.** A child run whose only work is read-only analysis (inspection, evidence gathering, projection, recommendation) does not constitute a Repository G2 effect. It must not be treated as requiring G2 execution authority, repository write capability, or a gated effect graph. The Controller must not require a G2 effect packet for read-only analysis child steps.

2. **WAIT_CONTROLLER invalid if runnable read-only work exists.** When the only remaining delegated work is runnable read-only analysis, the Controller MUST NOT emit `WAIT_CONTROLLER` as a blocking verdict. `WAIT_CONTROLLER` is valid only when the next actionable step requires human/gate authority or a capability the Executor lacks. Read-only analysis that the Executor can perform is `CONTINUE`-eligible.

3. **UR-G* vs GWC-G* naming separation.** UR-G* references the Ultimate Responsibility gate authority chain (human approval boundaries). GWC-G* references the GWC gate lifecycle (G0–G6). These are distinct naming spaces and must not be conflated in controller verdicts, envelope decisions, or audit records. A GWC gate decision is never a UR authority delegation, and a UR approval is never a GWC gate transition.

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
