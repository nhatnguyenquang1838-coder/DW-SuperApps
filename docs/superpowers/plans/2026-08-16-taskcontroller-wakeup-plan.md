# TaskController A2A Pilot — Wake-up Implementation Plan

Date: 2026-08-16
Design addendum: `docs/superpowers/specs/2026-08-16-taskcontroller-wakeup-addendum.md`
Tracking: #57; external Hermes host gap #59
Method: Superpowers `writing-plans` → TDD RED/GREEN

## Scope

Active lane: TaskController Agent Interaction / A2A.

Implement only the generic notification semantic discovered in the live pilot. Do not fix external Hermes packages/config by pretending repository core controls them.

## Task W1 — RED contract

Extend `tests/taskcontroller/test_reference_a2a.py` first.

Require:
- `WakeupSignal` deterministic round-trip;
- protocol `dw.taskcontroller.wakeup/v1`;
- required run/sender/recipient/mailbox_ref/seq/updated_at validation;
- `seq > 0`;
- `announces_new_work(cursor)` true only when actor/recipient matches and seq is newer than cursor;
- stale/equal seq false;
- no command payload fields in serialization (`request`, `inputs`, `artifact_refs`, `state` absent).

Expected RED: import failure because WakeupSignal does not exist.

Check exact-SHA TaskController CI and record RED evidence.

## Task W2 — GREEN primitive

Create `taskcontroller/interaction/wakeup.py` and export it from `taskcontroller/interaction/__init__.py`.

Implement immutable `WakeupSignal` plus deterministic `to_dict/from_dict` and cursor comparison. No Slack/GitHub SDK imports.

Check focused tests + full TaskController CI on exact SHA.

## Task W3 — Authority alignment

Update current TaskController interaction authority to distinguish:
- Agent data binding: GitHub reference mailbox;
- notification binding: optional pointer-only wake-up;
- Slack may host `SlackHumanControlPlane` and `SlackWakeupBinding` as separate semantics;
- wake-up carries no command payload;
- Executor must not reply with normal progress/tool chatter on wake-up transport.

Target files:
- `controllers/taskcontroller.yaml`
- `agents/shared/taskcontroller-a2a-protocol.md`
- `agents/chatgpt-agent/slack-controller-mvp.md`
- `agents/hermes/agent-instructions.md`
- activation contract tests where needed.

## Task W4 — Evidence and delivery

- exact-head TaskController CI green;
- global CI classified without fixing excluded Power compatibility lane;
- update PR #58 with live pilot + wake-up finding;
- keep #59 open for external Hermes host activation/silence closure;
- PR #58 remains Draft unless separate authority/review threshold is met.
