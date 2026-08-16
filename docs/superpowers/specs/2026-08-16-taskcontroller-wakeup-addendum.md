# TaskController A2A Pilot — Wake-up Notification Addendum

Date: 2026-08-16
Parent design: `2026-08-16-taskcontroller-reference-a2a-design.md`
Discovery: live pilot `TC-A2A-PILOT-20260816-01`
Status: approved by pilot evidence for implementation

## Problem discovered by live pilot

The GitHub reference mailbox proved the Agent **data path**: Hermes Cloud created one mailbox comment, then PATCHed that same comment from `seq=1 REPORT` to `seq=2 TERMINAL`, preserving one-actor-one-comment semantics and exact refs.

A second behavior was also proven: an idle Hermes Cloud session did not consume a newly published Controller mailbox sequence until it received an external notification. A compact Slack wake-up successfully resumed the session.

Therefore Agent communication has two distinct concerns:

1. **Data path** — canonical command/report payload and refs live in the Agent mailbox.
2. **Notification path** — optional pointer-only signal tells a non-polling Agent that a newer mailbox sequence exists.

These MUST NOT be collapsed back into Slack-as-command-bus.

## Architecture

```text
Controller
  |
  +-- publish A2AEnvelope --> Agent Mailbox (GitHub pilot)
  |
  +-- optional WakeupSignal --> Notification Binding
                               - Slack mention (pilot)
                               - webhook/push later
                               - provider-native signal later

Executor
  |
  +-- receives WakeupSignal
  +-- fetches canonical command from mailbox
  +-- updates own mailbox
  +-- emits no normal progress on notification transport
```

## WakeupSignal semantics

A WakeupSignal is intentionally **not an A2A command**.

Required fields:

```yaml
protocol: dw.taskcontroller.wakeup/v1
run_id: TC-...
sender: controller
recipient: hermes-cloud
mailbox_ref: github://.../issues/57#issuecomment-...
seq: 2
updated_at: ...
```

Invariants:

- pointer-only: no `request`, `inputs`, `artifact_refs`, code body or command payload;
- duplicate delivery is safe;
- Agent fetches canonical payload from `mailbox_ref` and validates `seq`;
- a stale signal (`seq <= last_seen_seq`) does not trigger work;
- notification binding IDs are never canonical TaskController IDs;
- notification transport is not progress/audit storage;
- no chain-of-thought or tool chatter is returned over the wake-up channel.

## Slack role

Slack may serve two **separate adapters** in the pilot:

- `SlackHumanControlPlane` — RootCard, semantic human timeline, human actions;
- `SlackWakeupBinding` — pointer-only Agent wake-up for an Executor that cannot push-subscribe or poll its mailbox while idle.

Sharing Slack as a physical transport does not merge these semantics. SlackWakeupBinding carries no Controller command body and no Executor progress body.

## Audit

Wake-up delivery may be audited as bounded metadata (`run_id`, actor, mailbox_ref, seq, delivery status) when useful, but it is not required to duplicate the canonical A2AEnvelope payload. The canonical semantic command/report audit remains `A2AEnvelope -> AuditEvent -> Run Ledger`.

## Acceptance

1. typed WakeupSignal deterministic round-trip;
2. invalid/stale signal fails closed or is deterministically ignored;
3. type cannot carry command/context/artifact payload fields;
4. mailbox cursor can decide whether the signal announces unseen work;
5. canonical instructions distinguish Agent mailbox data path from notification path;
6. Slack wake-up documentation requires silence after wake-up;
7. TaskController exact-head CI remains green.

## External host finding

Live pilot also showed Hermes Cloud still emitted Slack tool/progress narration and visibly loaded `gwc-task-controller`. That host-specific activation/silence gap is tracked separately in GitHub #59. Core WakeupSignal implementation does not pretend to fix an external host package/configuration that has not yet been updated.