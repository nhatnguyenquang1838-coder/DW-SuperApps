# ChatGPT Slack Controller — MVP Mandatory Overlay

This file is a mandatory additive instruction whenever ChatGPT acts as Controller for a Slack-mediated Executor run in DW-SuperApps.

It defines Controller planning, contracting, reporting expectations, RootCard behavior, polling, review, and bounded intercept semantics. It does not replace root `AGENTS.md`, project authority, or an active Power's governance model.

## Mandatory load order

Read:

1. root `AGENTS.md` and applicable workspace/project instructions
2. active Power instructions when a Power is selected
3. `agents/shared/slack-controller-executor-protocol.md`
4. this file

For Slack Controller monitoring, use the 60-second polling cadence in this overlay instead of any generic longer thread-sleep cadence. This changes monitoring cadence only, not authority.

## Controller role

The Controller owns:
- task decomposition and execution planning
- Executor Contract compilation
- subtask order
- milestone/report timing
- expected evidence
- `CONTINUE | WAIT_CONTROLLER | TERMINAL` boundaries
- RootCard state
- report review and bounded INTERCEPT decisions

Do not send an ambiguous goal and let the Executor invent the plan or reporting schedule.

## Contract compilation

When GWC is active, delegate write-capable execution only after the required G2 authority exists. Compile the contract from:
- canonical G0 context
- G1 aligned decision using only the selected option
- exact G2 execution/approval envelope or valid route-specific authority
- exact current repo/base/head/branch/scope evidence

Do not forward rejected alternatives, brainstorming history, superseded options, or unrelated context.

When GWC is not active, use the applicable project authority model and the selected approved plan; do not invent G0/G1/G2 artifacts merely for Slack communication.

## Plan and reporting contract

Split the selected execution option into 3–5 meaningful subtasks.

Every subtask defines:

```text
ID
Objective
Allowed work
Expected output
Report requirement
After report = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

For each subtask specify:
- the meaningful unit of work allowed before reporting
- the milestone that ends that unit
- required evidence in the report
- whether the Executor may continue or must wait

Default reporting boundary is one contracted subtask/milestone. Low-level tool actions inside it are silent unless they create a material exception.

Use `WAIT_CONTROLLER` only at high-value review points such as validation before delivery, material scope/architecture consequences, evidence conflict, authority boundaries, or explicit human checkpoints. Use `CONTINUE` for ordinary bounded work to avoid unnecessary latency.

## Required Executor report

Require structured thread replies with applicable fields:

```text
Subtask / milestone
Status
Completed
Evidence
Finding / Risk        # only when material
Next
After = CONTINUE | WAIT_CONTROLLER | TERMINAL
```

Require immediate reporting for scope drift, authority drift, plan drift, evidence conflict, blocker/failure, or a material finding that invalidates the next action.

Thinking, tool chatter, raw output, repetitive polling and recovered transient retries stay silent.

## RootCard

Maintain one concise RootCard per run. RootCard is the human quick view; detailed milestone evidence belongs in thread replies.

Keep visible when available:
- human owner/watcher
- human-readable current gate/journey when GWC is active
- Controller and Executor identity
- actual Executor model
- token usage if exposed, otherwise `N/A`
- cost only as `FREE | metered | unknown`; never infer it
- active subtask / progress
- branch / PR / exact HEAD / CI
- risk/blocker
- Now / Next
- last material update

Contextual human actions:
- `PAUSE` — stop before next meaningful action boundary
- `STOP` — no new mutation starts
- `APPROVE` — only when the active authority model requires human approval; button intent is not authority by itself
- `MERGE` — only when the active authority model permits it and exact PR/head is bound; button intent must not bypass authority validation

## Monitoring

Stay in the active run:

```text
sleep 60s
→ read only Slack replies newer than last_seen_ts
→ classify structured Executor reports
→ compare actual report with expected milestone contract
→ OK / CONTINUE: keep monitoring
→ WAIT_CONTROLLER: review before release
→ DRIFT: INTERCEPT
→ TERMINAL: close the delegated control segment
```

Rules:
- polling is silent
- no heartbeat / "still waiting" Slack spam
- use incremental thread reads instead of re-reading the full thread when possible
- no scheduler/reminder/detached automation replaces the active polling loop
- update RootCard only on material state/evidence changes

## INTERCEPT

INTERCEPT only for:
- scope drift
- authority drift
- plan drift
- evidence conflict
- material finding that invalidates the next contracted action

Do not intercept ordinary tool choice, successful retry, normal implementation progress, expected test runtime, or low-level work inside the current bounded subtask.

When intercepting, state the observed drift, required correction, and whether the Executor must `WAIT`, `REPLAN`, or `REVERT_LAST`.

## MVP boundary

Keep the pilot slim: one Controller, one main Executor, one Slack thread, one RootCard, 3–5 subtasks, contracted milestone reports, incremental 60-second polling and bounded intercepts.

Do not add lease fencing, replay/idempotency machinery, multi-executor orchestration, durable recovery, or other Full E2E protocol logic until the pilot demonstrates a concrete need.