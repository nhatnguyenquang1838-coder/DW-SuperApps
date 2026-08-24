# ChatGPT Slack Human Plane — TaskController A2A Overlay

This file is mandatory whenever ChatGPT is TaskController and Slack is used for human control/visibility. It is a Human Plane overlay only; machine command/progress/recovery transport remains the GitHub reference mailbox defined by `agents/shared/taskcontroller-a2a-protocol.md`.

## Mandatory load order

Read:

1. root `AGENTS.md` and applicable workspace/project instructions;
2. `controllers/taskcontroller.yaml`;
3. `agents/chatgpt-agent/agent-instructions.md`;
4. `agents/shared/taskcontroller-a2a-protocol.md`;
5. `agents/shared/taskcontroller-human-plane-policy.md`;
6. this file.

Slack Canvases are optional projections and must not block TaskController activation.

## Slack is the Human Control Plane

Slack is the Human Control Plane and semantic timeline. It may show one concise RootCard plus bounded semantic lifecycle events. Do not use Slack thread replies as the Executor progress transport, command bus, recovery journal, or continuation store.

Keep visible when material:
- human owner/watcher;
- current governed journey/gate when applicable;
- Controller/Executor identity;
- branch / PR / exact HEAD / CI;
- active contracted milestone;
- risk/blocker;
- Now / Next;
- last material update.

The RootCard is a projection, never machine authority. Human actions such as PAUSE/STOP/APPROVE/MERGE are intents whose authority must still be validated against the active repository/project contract.

## Slack reply rendering

For TaskController human-plane replies:
- prefer Slack Block Kit for structure;
- render rich text fields as `mrkdwn`;
- always include a plain-text fallback for accessibility/notification surfaces;
- keep lifecycle updates inside the canonical TaskController thread;
- suppress duplicate progress replies when mailbox seq and material state are unchanged;
- use Slack only for concise human-visible consequences, never as machine progress transport.

## A2A mailbox boot before Slack delegation

Before the first Executor dispatch in a TaskController session, ChatGPT MUST have:
- one durable Controller mailbox ref;
- one durable Executor mailbox ref;
- a persisted continuation checkpoint with both refs and mailbox cursor/expected seq;
- exact readback of the Controller mailbox carrying the same checkpoint.

If this cannot be established, stop delegation with `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED`. Do not put the command body into Slack as a fallback.

## Pointer-only wake-up

`SlackWakeupBinding` is notification transport only.

A wake-up MUST NOT include the command request, input refs, artifact payload, continuation state, code, diff, test output, or progress report. It contains only the pointer semantics needed for the Executor to fetch newer mailbox state, such as run, recipient, mailbox ref and seq.

After a wake-up, the Executor reads the canonical command from its Agent mailbox and its semantic result goes to its Agent mailbox. Human control input, wake-up delivery and Executor progress transport are separate concerns.

## Monitoring

Stay in-session using adaptive polling from `controllers/taskcontroller.yaml`:

```text
start at 60s
→ read only the exact Executor mailbox comment named by the continuation poll target
→ compare mailbox seq to mailbox cursor
→ stale/equal: ignore silently and back off 60s → 120s → 180s
→ newer semantic result: validate against the contracted milestone and reset cadence to 60s
→ update continuation/cursor
→ project only material human-visible consequences to Slack
```

Rules:
- polling is silent;
- 180 seconds is the maximum configured polling delay;
- no heartbeat or waiting spam;
- no whole Slack-thread replay for machine recovery;
- no scheduler/reminder/detached automation replaces an active required polling loop;
- update RootCard only on material state/evidence changes.

## INTERCEPT

INTERCEPT only for material scope drift, authority drift, plan drift, evidence conflict, execution past a WAIT boundary, or a material finding invalidating the next contracted action. Ordinary tool choice, successful retry, normal implementation progress, and test runtime stay inside the bounded Executor run.

## Recovery

Slack history is not a recovery dependency. Recover machine state from current repository/run identity, Controller mailbox continuation, Executor mailbox/cursor, exact PR/SHA/CI/artifact refs, and configured audit continuation manifest. Slack contributes only the RootCard binding needed for human continuity.
