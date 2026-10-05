# ChatGPT Agent Instructions — DW-SuperApps

These instructions are an additive overlay on root `AGENTS.md` and applicable workspace/project/Power instructions.

## Default role

ChatGPT may act as analyst, planner, reviewer, orchestrator, or Controller according to the active task. Repository/project authority remains defined by root and active project/Power instructions.

## TaskController activation — mailbox first

Any explicit TaskController activation MUST load current repository instructions before planning, delegating, posting to Slack, or claiming the controller is booted.

Required composition includes root/project instructions, `controllers/taskcontroller.yaml`, this file, `agents/shared/taskcontroller-a2a-protocol.md`, and when Slack is the human plane, `agents/shared/taskcontroller-human-plane-policy.md` plus `agents/chatgpt-agent/slack-controller-mvp.md`. Do not substitute conversation memory, prior Slack history, prior session summaries, external Slack policy documents, Power-local copies, or stale host instructions for this load chain.

TaskController activation is incomplete until the A2A transport is booted for the run:

1. materialize/recover exactly one Controller GitHub reference mailbox;
2. materialize/recover exactly one Executor GitHub reference mailbox;
3. persist the bounded `dw.taskcontroller.continuation/v1` checkpoint with mailbox pointers/cursors and exact head;
4. write the Controller mailbox with the same checkpoint and exact-read it back;
5. only then send any provider wake-up or first Executor dispatch.

If any required mailbox/checkpoint/readback cannot be established, activation `BLOCKED` with `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED`. Do not fall back to Slack as the machine command, progress, or recovery transport.

The repository-canonical human-plane policy is the only TaskController Slack policy input. Do not load or reconcile external Slack-hosted policy documents during activation.

## High-integrity Controller admission

When the controlled task activates an external governance/gate model, needs human approval for an effect, or binds execution identity to exact digests, treat it as a high-integrity Controller run.

Before dispatch, correction, approval presentation, or semantic resume:

1. resolve TaskController activation with `requires_v2_semantics=true`;
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

## Machine communication invariant

The GitHub reference mailbox is the machine interaction binding.

Before every new COMMAND or CORRECTION:

```text
advance Controller seq
→ persist continuation
→ update Controller mailbox in place
→ exact-readback same mailbox/seq
→ pointer-only wake-up when required
```

During active execution:

```text
sleep configured cadence
→ read only the exact Executor mailbox comment from the continuation poll target
→ reject stale/equal seq
→ validate the bounded semantic report
→ continue | review | intercept | terminal
```

Do not use Slack thread replies as the Executor progress transport. Do not reread whole Slack threads or GPT history to recover machine state when mailbox/continuation references exist.

## Slack invariant

Slack is the Human Control Plane. RootCard/thread content is a compact semantic projection and optional pointer-only wake-up surface, not the canonical command/progress journal. Raw A2A payloads, tool chatter, repetitive polling, and recovered transient retries stay out of Slack.

Executor semantic results are consumed from the Executor mailbox and then projected to Slack only when human-visible state materially changes.
