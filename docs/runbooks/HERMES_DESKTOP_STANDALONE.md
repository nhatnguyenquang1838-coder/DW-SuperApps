# Hermes Desktop — Standalone Mode Runbook

**User-defined mode:** One persistent **Hermes Desktop main session** runs to a verified outcome without calling an external **GPT Web / in-app-browser Controller**. When a Controller decision is required, the same host performs a separately bound **Controller phase**: Pattern E fanout → MoA synthesis → canonical Controller mailbox transition. The **main session**, designated Executor for the work, then reads the new Controller mailbox event and continues execution.

**Not a separate runtime, plugin, approval engine or second standing Executor.** For external GPT Web communication, use [Coordination Mode](HERMES_DESKTOP_COORDINATION.md) instead. This runbook defines the session operating pattern; canonical TaskController contracts decide whether an in-session Controller phase may actually produce a machine transition. Mere role-playing or a prompt saying "Controller" never grants that binding.

## 1. Definitions and admission

- **One continuous session** means one enduring Hermes Desktop *main Executor* session. Pattern E may call existing specialist Bot Chat sessions as **temporary advisory tools**, but does not create a second main session or communicate with GPT Web.
- **No outside GPT calls** means no GPT Web exchange, browser injection, Drive Preview handoff or external Controller conversation. It does **not** mean network-offline: the GitHub canonical mailbox and Pattern E's gateway/model backends may use network services. If literal offline execution is required, this binding must be redesigned and approved separately.
- **Logical Controller phase** is a serialized, explicitly authorized invocation of the *canonical TaskController Controller* from the Desktop host. It has its own validated identity, producer namespace, mailbox writer and continuation. **Executor and Controller cannot write each other's streams.** The same UI session does not collapse their authority boundaries.
- **Phase-exclusivity invariant:** a Controller decision phase is entered only after the Executor's semantic report has been persisted/read back and Executor effects are quiescent; the Controller event must be committed/read back before returning to Executor. No concurrent Controller and Executor writers, recursive self-dispatch or overlapping \`/goal\` turn.
- **Executor phase** belongs to the main Hermes session. It may use native `/goal` to implement one bounded approved contract. Routine test/fix loops do not invoke Controller.
- `max_children` specifies **TaskController child-run authority**, not whether the Desktop uses Standalone or Coordination mode. `max_children=0` forbids delegating governed Executor child runs. Controller-phase **read-only advisory Pattern E** is a separate scoped analysis capability, never disguised as an Executor child or given mutation authority.
- Where a run is already bound to a **GPT Web Controller**, Standalone must **not** silently take over Controller identity. First obtain and materialize the canonical Controller reassignment/continuation and required authority. Until then, stay paused or execute only an already-valid contract.

## 2. Canonical source order

Read [root AGENTS.md](../../AGENTS.md), `workspace.yaml`, [TaskController registry](../../controllers/taskcontroller.yaml), [agent index](../../agents/README.md), [A2A protocol](../../agents/shared/taskcontroller-a2a-protocol.md) and [Hermes Executor overlay](../../agents/hermes/agent-instructions.md). GWC activates only if the controlled task requires it. For child-repository writes load [Executor worktree policy](../../controllers/executor-worktree-policy.md) and [isolated worktree runbook](ISOLATED_SUBMODULE_WORKTREE.md).

For advisory fanout consult the externally managed [`dwa-a2a-coordination` Pattern E — SlackFanout source](https://github.com/nhatnguyenquang1838-coder/hermes-sync/blob/67e332fb2ef3d2cd0e86e0b8f1a20fcf3d235bb6/skills/dwa-a2a-coordination/SKILL.md). Pattern E's verified original entrypoint accepts a task string through `~/.hermes/dw_superapps/fanout.py`, consults specialist Bot Chat sessions, and optionally synthesizes one MoA assessment. **Adapting the Slack-ingress script for a Controller-phase decision inside Desktop is proposed, not verified on the current host**; inspect actual installed skill, script and provider before invocation. Historical v1 mutable-mailbox/Slack-poll instructions in that skill are *not* authoritative for current mailbox/v2.

## 3. Continuous operating sequence

```text
MAIN HERMES DESKTOP SESSION (persists)
  BOOT canonical run and bind main Executor
     |
  Have a valid Controller event and current execution authority?
     | YES
     v
  EXECUTOR: exact-read Controller event/cursor and continuation → PRECHECK
     |
  EXECUTOR: one native /goal → implement → test → in-scope fix → verify
     |
     +-- ROUTINE WORK --> continue in same goal, no Controller exchange
     |
     +-- HARD DECISION NEEDED --> publish typed Executor progress/blocker
     |                             (exact readback)
     |                             |
     |                  SWITCH to permitted CONTROLLER PHASE
     |                     exact-read Executor event
     |                     Pattern E read-only specialists → MoA
     |                     verify advice against exact current sources
     |                     check human/authority gate and source bindings
     |                     materialize new Controller event + continuation + cursor
     |                     exact readback
     |                             |
     |                  SWITCH BACK to MAIN EXECUTOR PHASE
     |                     consume newer Controller event exactly once
     |                     re-PRECHECK lease/fence/scope/pause/source
     |                     resume native /goal only if still authorized
     |                             |
     +-----------------------------+
     |
     +-- VERIFIED FINISH --> typed Executor SUCCEEDED/evidence + readback
                               |
                       Controller phase verifies final outcome/next gate
                               |
                             IDLE
```

For first mission bootstrap, an admitted Controller phase can prepare the **initial** Controller event before any Executor effect, but only if this session is already bound as an authorized Controller host; no implicit bootstrap from an expired GPT Controller run.

### A — BOOT / PRECHECK

Exact-read bound Controller/Executor mailbox events and cursors, immutable continuation, run/node/attempt identity, source/base/head, scope, approval, **current** lease and fence, idempotency and user pause. Reject stale seq, duplicate/conflicting digest, missing actor permission or any unavailable canonical materializer. The initial state is **PAUSED** whenever the user has paused the Desktop; no self-resume.

### B — EXECUTOR (main session)

Only after valid `EXECUTE` authority, run one native `/goal` to cover the ordered work packages and continue-until criteria. Recheck lease/fence before protected effects and on a resume. In-scope RED/GREEN, lint, tests, refactoring and repairs **stay inside** the goal. Never stop just to ask the Controller for an ordinary coding choice. `/goal` completion and `last_stop_reason` are UI state, not task evidence.

### C — CONTROLLER (serialized internal phase, as needed)

Stop Executor effects first. Publish/read back a typed Executor status/blocker or final result when contracted. Enter Controller logic **only** through a validated Controller actor binding. Exact-read the newer Executor event, classify the decision, and ground specialist prompts with exact repo/SHA/task/evidence. Use **Pattern E fanout → optional /moa synthesis** for advisory inputs when the Controller decision warrants it; the synthesis never grants rights or replaces source verification.

For the chosen decision, apply the canonical gate and Human authority rules. A decision requiring new Human approval **must pause**; no self-approval, fabricated signature, lease extension, scope widening, role impersonation or approval inferred from MoA consensus. If permitted, materialize exactly one typed **Controller** successor through runtime-owned APIs, persist continuation and cursor, and exact-readback.

### D — RETURN TO EXECUTOR

Change *operating phase*, not history. The main Executor exact-consumes the newer Controller event through its bound mailbox and reruns PRECHECK. Resume `/goal` under the updated valid contract only; dedupe by canonical event identity/sequence so a repeated signal never repeats effects.

### E — TERMINAL

Write exact test, diff, head/CI and acceptance evidence to a typed Executor result (or one canonical blocker). Controller verifies the semantic end condition and transition. Do not report complete solely because the session/goal stopped. No PR/merge/deploy/production or other separately governed effect without its actual authority.

## 4. Loop state, liveness and stop conditions

| State | Action | Continuity invariant |
| --- | --- | --- |
| `PAUSED` | No effects or automatic resume | An old Loop tick or expired Controller event cannot wake work |
| `EXECUTOR_ACTIVE` | Continue bounded goal | No repeated Controller turn for ordinary test/fix |
| `CONTROLLER_REQUIRED` | Report exact Executor event and switch phase | Never silently invent authority |
| `CONTROLLER_ANALYSIS` | Pattern E → MoA advisory + verified decision | No machine mutations by specialist advice |
| `AUTHORITY_REQUIRED` | Materialize real actionable Human request; stop | No self-approval or fake next lease |
| `CONTROLLER_PUBLISHED` | Exact readback of new Controller event/cursor | Only canonical materializer may write |
| `EXECUTOR_RESUME` | Consume newer event; fresh precheck | No replay of old work |
| `TERMINAL` | Verified result and next action | Session can idle; no polling |

The main session can continue *without GPT Web*, but it cannot guarantee infinite progress: missing authority, missing Pattern E/provider capability, material plan drift, user pause and unresolvable dependency produce truthful STOP/BLOCKED outcomes. A read-only advisory limitation must not be silently converted into effect authority.

## 5. SCRUM-781 guard

The recorded GPT Controller E9 event `#6058394365` and continuation record 23 are **not** an in-session Controller binding. The Executor E5 was at logical seq 1, the lease expired `2026-10-08T14:24:04Z`, and the historical Hermes Loop was user-paused at tick 645. **Do not resume the old event, create a replacement Controller identity or turn on Standalone execution from this runbook.** Controller transfer/recovery, fresh exact authority and removal of user pause are separately required.

## 6. Acceptance criteria

- [ ] Exactly one persistent main Hermes Desktop Executor session; no GPT Web/browser/Drive Preview path.
- [ ] Any in-session Controller phase uses an explicit *canonical* Controller actor binding and separate writer; never self-approves.
- [ ] Pattern E and MoA are advisory, grounded to exact current sources, with no child effect authority.
- [ ] `max_children=0` prohibits governed Executor child runs but does not automatically prohibit separately authorized read-only Controller analysis.
- [ ] Every Controller/Executor switch persists an exact typed mailbox event/cursor and continuation; event sequences are monotonic and idempotent.
- [ ] Native `/goal` starts only after current PRECHECK; routine RED/GREEN/fix remains continuous.
- [ ] Hard blocker/Human gate yields a durable actionable stop, never fake progress.
- [ ] Paused/expired SCRUM-781 state is unchanged; live Desktop Pattern E/Controller-role switching not claimed as tested.
