# Hermes Desktop — Coordination Mode Runbook

**User-defined mode:** Hermes Desktop's **main session remains the Executor**. The **GPT Web session in the bound in-app browser is the Controller**. After Hermes writes and exact-readbacks a typed Executor mailbox event, it uses the available **`drive_preview` / bound browser-preview capability** to notify GPT Web to consume that event. GPT Web reads the canonical mailbox, resolves the Controller decision and writes a new Controller mailbox event. Hermes consumes the new Controller event, prechecks it and continues.

**This is external GPT Web coordination, not multi-bot delegation.** For same-session Controller Pattern E → MoA choose [Standalone Mode](HERMES_DESKTOP_STANDALONE.md). The choice of mode is about **where Controller runs and how notifications are delivered**, not `max_children` or the size of the work package.

## 1. Roles, authority and transport

| Concern | Responsibility |
| --- | --- |
| Hermes Desktop main session | **Executor**, owner of Executor event/cursor, implementation, verification and report |
| GPT Web bound thread | **Controller**, owner of Controller event/cursor, next decision and Human authority routing |
| GitHub mailbox/v2 | Canonical typed machine event, continuation, source and evidence; **sole source of machine truth** |
| In-app-browser / `drive_preview` | Sends a pointer to a **new exact mailbox event** and displays/returns GPT's response; **not** approval, command body or canonical state |
| User / Human | Explicit approval for separately governed effects, not a GPT/browser click surrogate |

**Availability/compatibility guard:** The existing [TaskController registry](../../controllers/taskcontroller.yaml) declares event-driven mailbox/v2, forbids periodic polling and Slack machine notifications, and lists `hermes-cloud` with a `mailbox-event` wakeup requirement. It does **not** establish that `drive_preview` exists, works in Hermes Desktop, or is an admitted provider-event adapter. This runbook documents the intended **Coordination UX**; before activating it, verify the installed Desktop preview tool and an **explicit approved transport binding** compatible with the active run. Do not silently replace a `mailbox-event` contract with browser signaling.

Historical Hermes messages reported `desktop_preview`/`drive_preview` unavailable in some sessions. Treat tool-absence, unbound thread, broken return visibility, mismatched session identity and unavailable GPT Web GitHub read/write capability as **TRANSPORT_BLOCKED**, not as permission to fake a response or switch to another browser/Slack/polling.

## 2. Boot and prerequisites

Read [root AGENTS.md](../../AGENTS.md), `workspace.yaml`, [TaskController registry](../../controllers/taskcontroller.yaml), [agent index](../../agents/README.md), [A2A protocol](../../agents/shared/taskcontroller-a2a-protocol.md), [Hermes instructions](../../agents/hermes/agent-instructions.md), and applicable activated GWC/project instructions. For registered child-repo mutations also read [worktree policy](../../controllers/executor-worktree-policy.md) and [isolated worktree runbook](ISOLATED_SUBMODULE_WORKTREE.md).

Resolve and exact-read:
- run/node, Controller/Executor actor and mailbox bindings, event/cursor sequences, immutable continuation, source refs/branch/head;
- the **single bound GPT Web thread** and browser/preview tool capabilities;
- mode-specific admitted provider notification binding and readiness;
- exact attempt, live approval/lease/fence, approved scope, user pause and effect boundaries.

The selected GPT Web thread must be the Controller for this exact run. Merely opening any ChatGPT page does not establish identity. Failure to satisfy one precondition means no effect execution.

## 3. Two-way continuous cycle

```text
HERMES DESKTOP (MAIN EXECUTOR)                GPT WEB (CONTROLLER)
────────────────────────────────────────────────────────────────────
BOOT exact current Controller event  ◀── prior Controller mailbox event
  → PRECHECK lease/fence/scope
  → native /goal: implement/test/fix
  → milestone, blocker or verified completion
  → append typed EXECUTOR event
  → exact-readback Executor event + cursor
  → drive_preview: send pointer ────────────────▶ GPT Web bound thread
                                                     exact-read Executor event
                                                     validate seq/digest/evidence
                                                     decide CONTINUE / WAIT / TERMINAL
                                                     resolve Human authority if needed
                                                     persist continuation + Controller event
                                                     exact-read Controller event/cursor
                      GPT Web reply or provider event ◀── pointer to Controller event
  → exact-read new Controller event/cursor
  → PRECHECK new lease/fence/scope/pause
  → continue /goal only if valid
  → repeat at the next semantic boundary
────────────────────────────────────────────────────────────────────
```

**Do not message GPT Web on every RED/GREEN/test/fix.** Continue routine implementation in Hermes until a contracted semantic milestone, hard blocker or final result. Then perform a **single** handoff per newer Executor mailbox event.

### A — EXECUTOR milestone and durable report

Hermes must create the result using the canonical mailbox/v2 repository/materializer, **not handwritten GitHub JSON**. Record run/node, event sequence/digest, progress/result class, evidence refs, head and next boundary; exact-readback event and cursor. Do not use a browser message as the result itself.

### B — SEND via bound Drive Preview

Only after step A succeeds, use the verified **Hermes Desktop in-app-browser + `drive_preview`** to notify the **bound GPT Web Controller thread**. The message is pointer-only:

```text
TASKCONTROLLER_EXECUTOR_EVENT_READY
run_id: <canonical run ID>
executor_mailbox_ref: <exact canonical ref>
executor_seq: <new typed sequence>
event_digest: <observed canonical digest or exact event ref>
action: Controller exact-read and process this event; reply with exact Controller event ref.
```

The pointer does not carry effect commands, raw secrets, approval tokens, speculative scope or agent thought traces. Store a dispatch correlation/notification receipt if the approved provider offers one. A notification-delivered indicator is not proof GPT actually consumed the mailbox.

### C — GPT Web Controller consumes and decides

GPT reads the exact newly referenced Executor event/cursor through its authorized GitHub connection, validates identity/digest/lease/evidence and invokes **canonical** Controller transition/admission logic. It alone handles Human approval, current source binding, the successor plan and authorized next effect. Write and exact-readback the new Controller event/cursor and durable continuation **before** claiming release.

A GPT chat reply such as "APPROVED" or "continue" without a valid Controller mailbox successor is **not** execution authority. On genuine Human wait, materialize an actionable request and stop until approved; never mint approval based on ChatGPT text.

### D — REVERSE notification and Hermes resume

Use the same **approved bound preview channel** to convey the Controller event pointer back to Hermes, **if the installed tool can actually observe and deliver that reply**; otherwise the run is `TRANSPORT_BLOCKED` pending an authorized event adapter or explicit manual handoff. No background browser polling or mailbox polling.

Hermes exact-reads only the newer canonical Controller event, validates monotonic seq/digest/continuation, fresh lease/fence/scope/source/actor and user pause, then resumes `/goal` only within that new authorized boundary. Duplicate browser notifications and stale GPT replies must not repeat repository effects.

### E — TERMINAL / recovery

The Executor's verified completed evidence goes to its mailbox; GPT Controller validates and records the terminal decision. On ambiguous status, tool loss, disconnect, failed event readback, source drift or expired approval, stop safely and preserve continuation. Recovery starts from canonical mailbox/cursor and exact provider receipts, not from conversation replay. Browser transport never owns run state.

## 4. Continuity and anti-stuck matrix

| Condition | Hermes action | GPT action |
| --- | --- | --- |
| Ordinary in-scope test/fix | Keep executing locally; do not notify GPT | No action |
| New Executor event exact-readback | Send one pointer via bound preview | Read & validate event once |
| GPT busy/late | Preserve WAIT state; no repeated instruction or busy-loop | Reply when processed |
| Duplicate preview delivery | Dedupe by event identity, no extra effect | Dedupe Controller processing |
| GPT Web responds without mailbox successor | Stay blocked; do not treat prose as approval | Create valid successor or explicit blocker |
| Preview unavailable/unbound | Stop with transport blocker | Do not assume message arrived |
| Controller successor valid | Exact-read and re-PRECHECK, then continue | Maintain canonical continuation |
| Lease expired/user paused | No effects, no auto-resume | Resolve authority/pause legitimately |
| Verified mission complete | Publish typed evidence and stop implementation | Validate terminal / next gate |

## 5. SCRUM-781 transition warning

SCRUM-781 Controller E9 continuation record 23 was `WAIT_EXECUTOR / AWAIT_EXECUTOR_EVENT`, Executor E5 last logical seq was 1, and the approval/lease expired `2026-10-08T14:24:04Z`. The Loop was user-paused at tick 645. **This runbook does not authorize switching E9 from `mailbox-event` to preview delivery or waking the old run**. A Controller-authorized binding change, current authority, approved Desktop preview transport and explicit release of the user pause are prerequisites for a real Coordination run.

## 6. Acceptance criteria

- [ ] Hermes Desktop is the sole main Executor; GPT Web bound thread is external Controller.
- [ ] After a **typed Executor mailbox write + exact-readback**, Hermes sends a pointer via **verified** in-app-browser / `drive_preview`.
- [ ] GPT Controller actually reads the exact Executor event and creates a runtime-owned **Controller** event/continuation/cursor.
- [ ] Hermes receives an observed successor pointer, fetches and validates the new Controller event **before** resuming any effect.
- [ ] One semantic handoff per new event; no duplicate execution, polling, Slack fallback or fake preview success.
- [ ] Tool/binding unavailable yields a truthful blocker and durable pause.
- [ ] No control authority inferred from chat prose, assistant synthesis, user pause, past approval or `/goal` completion.
- [ ] Real on-host tool availability and full round-trip remain **unverified** until a controlled end-to-end POC passes.
