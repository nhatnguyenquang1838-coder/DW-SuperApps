# ChatGPT Agent Instructions — DW-SuperApps

These instructions are an additive overlay on root `AGENTS.md` and applicable workspace/project/Power instructions.

## Default role

ChatGPT may act as analyst, planner, reviewer, orchestrator, or Controller according to the active task. Repository/project authority remains defined by root and active project/Power instructions.

## TaskController activation — mailbox first

Any explicit TaskController activation MUST load current repository instructions before planning, delegating, posting to Slack, or claiming the controller is booted.

Required composition includes root/project instructions, `controllers/taskcontroller.yaml`, this file, `agents/shared/taskcontroller-a2a-protocol.md`, and when Slack is the human plane, `agents/shared/taskcontroller-human-plane-policy.md` plus `agents/chatgpt-agent/slack-controller-mvp.md`. Do not substitute conversation memory, prior Slack history, prior session summaries, external Slack policy documents, Power-local copies, or stale host instructions for this load chain.

TaskController activation is incomplete until the canonical mailbox/v2 transport is booted for the run:

1. materialize/recover exactly one Controller mailbox/v2 reference;
2. materialize/recover exactly one Executor mailbox/v2 reference;
3. persist the bounded `dw.taskcontroller.continuation/v1` checkpoint with mailbox pointers/cursors and exact head;
4. materialize the Controller transition only through `taskcontroller/runtime/high_integrity_session.py::materialize_controller_transition`;
5. exact-read the append-only event, durable cursor, and continuation;
6. only then send any provider wake-up or first Executor dispatch.

A2A/v1 mutable-comment runtime is compatibility-only and requires explicit opt-in; it is never the default fallback.

If any required mailbox/checkpoint/readback cannot be established, activation `BLOCKED` with `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED`. Do not fall back to Slack as the machine command, progress, or recovery transport.

The repository-canonical human-plane policy is the only TaskController Slack policy input. Do not load or reconcile external Slack-hosted policy documents during activation.

## High-integrity Controller admission

When the controlled task activates an external governance/gate model, needs human approval for an effect, or binds execution identity to exact digests, treat it as a high-integrity Controller run.

Before dispatch, correction, approval presentation, or semantic resume:

1. resolve TaskController activation; mailbox/v2 is the default canonical protocol;
2. validate `taskcontroller/controlplane/controller_admission.py`;
3. use `dw.taskcontroller.mailbox/v2` typed envelope/event identity;
4. read only the exact bound mailbox reference/cursor;
5. use the canonical envelope/artifact digest as semantic identity;
6. resolve schemas through the canonical descriptor/source binding;
7. derive expected digests only from observed evidence or canonical recomputation;
8. derive preapproval state from the current verified boundary, never by materializing the target gate's required artifact first;
9. present a human approval only from the typed approval-request artifact plus verified command digest;
10. for the GitHub high-integrity binding, use `taskcontroller.interaction.github_continuation_store.GitHubContinuationStore` to persist/exact-read the bounded continuation before dispatch;
11. only after continuation persistence PASS, use `taskcontroller.interaction.github_mailbox_v2.GitHubMailboxRepository`: append typed event/cursor records as new issue comments and never update a mutable actor comment in place.

Fail closed instead of falling back to the mutable v1 compatibility lane.

Forbidden in a high-integrity run:

- hand-authoring or directly posting machine-state JSON/records to GitHub instead of using the canonical v2 materializer;
- supplying runtime-owned `record_type`, event/cursor sequence, previous-digest, event-digest, or continuation-chain fields;
- persisting raw token/secret/credential values in mailbox payloads; use durable refs/digests;
- inventing an ad-hoc Controller/Executor Markdown protocol;
- treating SHA-256 of an entire mutable GitHub comment body as semantic identity or approval identity;
- rereading/scanning the whole GitHub issue as machine-state recovery when an exact mailbox ref exists;
- hard-coding a predicted hash/digest and requiring the Executor to match the prediction;
- guessing a schema path when the producer/node descriptor names the canonical schema;
- resolving the target gate as BLOCKED because the authority artifact being requested does not exist yet.

Transport-body hashes may be retained as diagnostic evidence, but they never supersede typed envelope/artifact identity.

## Controller contracting

The Controller owns task decomposition, selected-plan contracting, milestone/report timing, WAIT points, RootCard projection state, mailbox cursors, report review, continuation checkpoints, and bounded INTERCEPT decisions. The Controller must not delegate an ambiguous task and allow the Executor to invent its own plan or reporting cadence.

If an additional project or Power governance system is explicitly active for the controlled task, the Controller must honor that system's exact write/authority contract before delegating protected execution. TaskController activation alone does not activate any Power.

Rejected alternatives, brainstorming noise, and superseded options must not be forwarded to the Executor.

## Plan-once / execute-end-to-end contracting

For new high-integrity Controller requests, declare exactly one `controller_contract_mode`:

- `PLAN`: research, source recovery, design, decomposition, scope/AC validation. No implementation authority and no repository mutation.
- `TRANSPORT_REPAIR`: repair mailbox/protocol/continuation transport only. No implementation authority.
- `EXECUTE`: a bounded implementation package after the applicable execution authority has been validated.

Do not keep an approved implementation in repeated read/validate/report-only commands. Once `EXECUTE` is active, the Controller must contract a meaningful engineering outcome, not a protocol step.

An `EXECUTE` contract MUST bind:

1. the exact approved plan/artifact reference;
2. the exact approval reference and canonical approval digest;
3. exact writable targets;
4. the real engineering actions authorized for this package;
5. ordered work packages/objectives;
6. acceptance criteria and `continue_until` completion conditions;
7. hard stop conditions;
8. exact source/base/branch or worktree binding.

The Executor owns implementation details inside that approved boundary. The Controller owns outcome, scope, authority ceiling, AC, integration ceiling, and hard stop conditions.

After execution authority becomes active, the default behavior is **continue working**. The Executor MUST NOT stop merely because:

- a RED test has been created;
- GREEN has been reached for one test;
- a test/lint/typecheck fails and the failure can be fixed inside scope;
- refactoring is needed inside approved files;
- a routine implementation choice is required;
- another approved test/fix cycle is needed.

The Executor should continue through implementation, TDD/test/fix loops, scoped refactoring, focused regression, staging, commit, push, and Draft PR when those actions are included in the approved package. A routine engineering failure is work to resolve, not a WAIT_CONTROLLER boundary.

Hard stop / WAIT_CONTROLLER is reserved for real boundary changes such as:

- source/base or execution-identity drift;
- need to modify a path outside approved writable scope;
- approved plan is materially invalid and requires replan;
- destructive, production, secret, migration, merge, or deployment authority is required;
- an external dependency/permission makes the approved outcome impossible;
- evidence proves an unresolved architectural decision outside the approved plan.

Do not ask for a new approval between RED, GREEN, refactor, test, commit, push, and Draft PR when one valid bounded execution package already authorizes those actions. Merge, Ready-for-Review when separately governed, deploy, release, production/data/secret/migration/destructive actions remain separate authority.

### Controller-owned HITL

ChatGPT Controller is the only actor in the Controller/Executor pair that communicates an approval/HITL request to the User. Never instruct an Executor to wait for the User directly. Never accept an Executor-emitted `WAIT_USER_*` or `WAIT_HUMAN_*` as a valid next state.

The required sequence is:

```text
Controller G0/G1 + authority preparation
-> Controller materializes exact HITL when required
-> User/authority resolves
-> Controller sends one executable mission contract
-> Executor runs through internal work packages
-> Executor COMPLETE or BLOCKED(reason)
-> Controller decides next gate
```

Executor BLOCKED reasons are limited to `AUTHORITY_BOUNDARY`, `SCOPE_EXPANSION`, `MATERIAL_PLAN_INVALIDATION`, and `EXTERNAL_DEPENDENCY_BLOCKED`. Routine engineering failures are never promoted into these classes when an in-scope repair path remains.

`EFFECT_HOLD` blocks named effects only and does not stop Controller reasoning/planning/read-only recovery. `RUN_HOLD` is the only hold that stops new run actions. Do not create or preserve an ambiguous generic HOLD.

When a boundary requires Human authority, materialize the actionable approval request in the Human Plane in the same Controller transition. Do not persist `WAIT_HUMAN_APPROVAL` unless that request exists. When authority is delegated, require a delegate dispatch receipt. Otherwise fail `AUTHORITY_REQUEST_UNROUTED` instead of waiting silently.

The executable guards for these semantics are `taskcontroller/controlplane/execution_contracting.py`, `taskcontroller/controlplane/orchestration_policy.py`, and `taskcontroller/controlplane/result_resume.py`. They validate the contract/outcome but never grant authority.

## Machine communication invariant

The append-only GitHub mailbox/v2 repository is the default machine interaction binding. The Controller never renders or posts transport JSON itself.

Before every new COMMAND or CORRECTION:

```text
bind semantic transition
→ validate contract/authority
→ persist + exact-read continuation
→ compile deterministic mailbox/v2 envelope
→ DispatchPrepared
→ append canonical event through GitHubMailboxRepository
→ exact-readback event
→ acknowledge durable producer cursor
→ exact-readback continuation
→ pointer-only wake-up when required
```

During active execution:

```text
before poll/wakeup → exact-read current Controller request + continuation
→ validate the bound execution attempt lease/fence at caller-supplied observed_at
→ if stale/expired/missing current fence: WAIT_CONTROLLER / RESOLVE_EXECUTION_AUTHORITY
→ otherwise sleep configured cadence
→ read only the exact Executor mailbox comment from the continuation poll target
→ reject stale/equal seq
→ validate the bounded semantic report
→ continue | review | intercept | terminal
```

Never keep `POLL_EXECUTOR` or send an Executor wake-up after the bound execution attempt lease/fence is stale or expired. A previously materialized approval remains historical authority evidence; it does not make an expired execution attempt current.

Do not use Slack thread replies as the Executor progress transport. Do not reread whole Slack threads or GPT history to recover machine state when mailbox/continuation references exist.

## Slack invariant

Slack is the Human Control Plane. RootCard/thread content is a compact semantic projection and optional pointer-only wake-up surface, not the canonical command/progress journal. Raw A2A payloads, tool chatter, repetitive polling, and recovered transient retries stay out of Slack.

Executor semantic results are consumed from the Executor mailbox and then projected to Slack only when human-visible state materially changes.
