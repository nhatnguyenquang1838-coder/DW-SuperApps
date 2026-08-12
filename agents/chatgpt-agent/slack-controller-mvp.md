# ChatGPT Slack Controller — MVP Overlay

Use this overlay when ChatGPT controls one Executor through Slack for a DW-SuperApps/GWC task.

Read first:

`agents/shared/slack-controller-executor-protocol.md`

This overlay adds Controller behavior only. It does not replace the repository/project authority model.

## Contract compilation

When GWC is active, delegate execution only after the required G2 authority exists. Compile the Executor Contract from the canonical task context, the selected aligned option only, the exact execution authority, and current repo/base/head/branch/scope evidence.

Do not forward rejected alternatives, brainstorming history, or unrelated context to the Executor.

## Subtasks

Split the selected execution option into 3–5 meaningful subtasks. Every subtask defines:

```text
ID
Objective
Allowed work
Expected output
Report requirement
After report = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

Controller owns the milestone/report schedule and WAIT boundaries.

## RootCard

Maintain one concise RootCard per run using the shared protocol. RootCard is the human quick view; detailed milestone evidence stays in thread replies.

## Monitoring

Stay in the active run:

```text
sleep 60s
→ read only Slack replies newer than last_seen_ts
→ compare actual report with expected milestone
→ continue | review | intercept | terminal
```

Do not use a scheduler/reminder/automation to replace the active polling loop. Polling itself is silent.

## Intercept

INTERCEPT only for scope drift, authority drift, plan drift, evidence conflict, or a material finding that invalidates the next contracted action.

Do not micromanage ordinary tool choice, successful retry, or normal implementation/test progress.
