# Hermes Desktop — Unified Runtime Runbook

**Status:** Desktop operating procedure (documentation); implementation and provider transport readiness must be verified separately.
**Scope:** Two autonomous AI peers (GPT and Hermes) share proposal/decision rights; the active execution-unit owner runs in one persistent Hermes Desktop session. Legacy Controller/Executor labels describe mailbox producer/writer responsibilities, **not** an AI seniority hierarchy. Controller strategy selects a transport at the existing invocation boundary.
**Authority:** This runbook does **not** implement or amend TaskController, grant approval, activate GWC, authorize writes, register a provider adapter, or make either mode immediately executable.

## 1. Canonical sources and mode selection

Before executing, read [root `AGENTS.md`](../../AGENTS.md), `workspace.yaml`, [Controller registry](../../controllers/taskcontroller.yaml), [agent index](../../agents/README.md), [TaskController A2A contract](../../agents/shared/taskcontroller-a2a-protocol.md), and [Hermes Executor instructions](../../agents/hermes/agent-instructions.md). For approved local mutations in a registered submodule also load [Executor worktree policy](../../controllers/executor-worktree-policy.md) and [isolated worktree runbook](ISOLATED_SUBMODULE_WORKTREE.md). Load GWC only when the actual task activates it.

Choose `controller_strategy` **from the admitted Controller identity and communication binding**, not from task complexity, `max_children`, number of test cycles, or operator preference after a failure:

| Strategy | Controller | Invocation | Main Executor |
| --- | --- | --- | --- |
| `standalone` | Separately admitted **in-session logical Controller phase** on Hermes Desktop | Pattern E specialist fanout → MoA (as needed) → verified Controller decision → typed Controller mailbox | Same **one** persistent Hermes Desktop session |
| `coordination` | **GPT Web** in an exact bound in-app-browser thread | Typed Executor event → verified `drive_preview` notification to GPT → Controller transition → successor pointer | Same **one** persistent Hermes Desktop session |

`max_children=0` prohibits **governed Executor child runs** but does not choose Standalone/Coordination. In Standalone, Pattern E specialist Bot Chat calls are **advisory under separately approved Controller-analysis scope**, not Executor child contracts or a new main session. “No outside calls” means **no GPT Web** in Standalone, not network-offline: GitHub mailbox, model and specialist calls may be remote.

**Controller strategy is bound at BOOT.** Moving between strategies or transferring a GPT-bound Controller to an internal Controller requires a new canonical authority/actor/continuation/notification binding transition. Never auto-fallback after preview or fanout failure.

### Peer collaboration and bounded autonomy (SCRUM-840 R3 — branch proposal)

- GPT and Hermes are **equal AI decision participants**. Either may initiate `PROPOSE → CHALLENGE → DISCUSS → CONVERGE → AGREE`; neither agent must obtain the other's permission for routine actions already covered by its admitted mission scope. "Controller" and "Executor" remain the *legacy wire-protocol roles* for the existing `controller_to_executor` / `executor_to_controller` mailbox/v2 envelopes. Do not silently swap their event namespaces or claim live symmetric transport support until qualified.
- A shared decision references one exact proposal digest plus **two separate actor-bearing endorsements**. `taskcontroller.controlplane.orchestration_policy.decide_peer_collaboration()` is a **pure advisory policy**; it does not persist endorsements, create an event, replace a run-specific approval, or grant authority. The existing canonical materializer/repository continues to own machine events and receipts.
- Each peer may reason, plan, challenge, review evidence, and implement **within its own valid delegated scope**. A bounded `EXECUTE` mission permits implement/test/fix/refactor/commit/push/Draft PR when these were granted; code failures and internal milestones do not require a new round-trip.
- Disagreements use a small finite discussion budget and one durable disputed-decision reference; only unresolved material scope/authority questions escalate to the Human. No third-party AI approver, no automatic self-grant or silent scope expansion.
- Keep **one active effect writer per execution unit** and independent identity/lease/fencing records per actor. Peer equality is not permission to act concurrently on the same worktree/branch or mutate another peer's mailbox.
- This is a **non-main engineering change**. Do not interpret it as a retroactive amendment to active #595, as an admitted Hermes Desktop session or as permission to resume its expired attempt 3.

## Controller-first bootstrap boundary (not an Executor PRECHECK)

This document is the **Executor-side** procedure, beginning when an admitted Executor consumes a real Controller command. A fresh run's Controller-owned `UR.G0` / `UR.G1` (or other native understanding/planning stages) may start, complete with native gate evidence and advance **without** a Hermes session, notification adapter, Executor acknowledgement or mailbox dispatch. The Controller decides the native gate owner first; it MUST NOT enter `WAIT_EXECUTOR`, mint a placeholder lease or send a command merely to initialize a new run.

`BOOT / PRECHECK` below applies to **Hermes when it receives an actual Executor-bound request**, and before every protected effect; it does not gate Controller-only planning. At the first real Executor dispatch boundary, the Controller must bind recipient/adapter, use the canonical mailbox/v2 materializer, persist continuation and exact-read event/cursor/continuation before wake-up. The Executor subsequently performs PRECHECK. Missing Desktop Preview or Executor admission blocks **dispatch**, not lawful Controller-only work; `RUN_HOLD` and native gate receipts are never bypassed.

## 2. Shared state machine (both modes)

```mermaid
stateDiagram-v2
    [*] --> BOOT
    BOOT --> PAUSED: user pause / invalid session
    BOOT --> PRECHECK: binding recovered
    PRECHECK --> EXECUTING: valid EXECUTE authority
    PRECHECK --> BLOCKED: invalid authority / drift
    EXECUTING --> VERIFYING: milestone / candidate complete
    VERIFYING --> EXECUTING: in-scope failure / remaining work
    VERIFYING --> REPORTING: semantic decision or verified result
    REPORTING --> CONTROLLER_REQUIRED: typed event persisted and read back
    CONTROLLER_REQUIRED --> INVOKING_CONTROLLER: adapter admitted
    CONTROLLER_REQUIRED --> BLOCKED: no admitted adapter
    INVOKING_CONTROLLER --> WAITING_CONTROLLER: pending external Controller
    INVOKING_CONTROLLER --> CONSUMING_CONTROLLER: successor event available
    INVOKING_CONTROLLER --> AUTHORITY_WAIT: human authority required
    INVOKING_CONTROLLER --> BLOCKED: transport / actor failure
    WAITING_CONTROLLER --> CONSUMING_CONTROLLER: observed valid successor pointer
    WAITING_CONTROLLER --> AUTHORITY_WAIT: actionable human gate
    WAITING_CONTROLLER --> BLOCKED: expired, cancelled, invalid delivery
    CONSUMING_CONTROLLER --> PRECHECK: new event read back / deduped
    CONSUMING_CONTROLLER --> TERMINAL: verified terminal Controller decision
    CONSUMING_CONTROLLER --> BLOCKED: schema / source / lease mismatch
    AUTHORITY_WAIT --> CONSUMING_CONTROLLER: new authorized event after human decision
    BLOCKED --> BOOT: explicit recovery and fresh binding
    PAUSED --> BOOT: explicit unpause and current boot
    TERMINAL --> [*]
```

State meanings:
- **`BOOT` / `PRECHECK`:** Resolve exact mailbox/v2 Controller/Executor events and cursors, immutable continuation, current source/base/head, actor identity, scope, approval, lease-generation/fence and user pause. PRECHECK precedes **every** protected effect, fresh goal and resume.
- **`EXECUTING` / `VERIFYING`:** Use one bounded native Hermes `/goal` when installed support and contract permit. Implement → test → fix → refactor → regression **within the same valid EXECUTE mission**. A recoverable RED/GREEN or lint error is **not** a Controller boundary. `/goal` judge, `last_stop_reason` or loop tick does not prove acceptance.
- **`REPORTING`:** Publish a **typed Executor mailbox/v2** progress/blocker/completion event via the canonical materializer; exact-readback the event, digest/cursor and evidence. No handwritten GitHub JSON, Slack message, Preview text or MoA output substitutes for it.
- **`INVOKING_CONTROLLER`:** **Only strategy-specific step.** Pass the exact already-persisted `executor_event_ref`. An adapter can produce a verified Controller event reference, an actionable authority wait, or an explicit blocker; external asynchronous notification may first yield `WAITING_CONTROLLER`.
- **`CONSUMING_CONTROLLER` / `PRECHECK`:** Exact-read a **newer** Controller event and immutable continuation with correct actor/run/attempt/seq/digest, lease/fence/source/scope/pause before resuming effects. Duplicate notification is no-op; old events cannot replay effects.
- **`AUTHORITY_WAIT` / `BLOCKED` / `PAUSED`:** No protected effects and no silent retry. Human request must be genuinely actionable and owned by the admitted Controller. Recovery requires verified new evidence/authority and an authorized trigger, never an automatic Loop. **Host scheduler paused ≠ TaskController RUN_HOLD ≠ terminal Executor.** Preserve the main session for exact event-driven successor delivery and identify Controller's release action; Loop tick count or `last_stop_reason` is not authority.
- **`TERMINAL`:** Both Executor evidence **and canonical Controller terminal disposition** are verified; otherwise wait for a valid Controller outcome.

### Shared transition invariants

1. **One main session, one active effect writer.** Executor and Controller actor identities/mailbox producer namespaces remain separate, even when both logical phases execute in the same UI session. No overlapping Controller/Executor writers or recursive self-dispatch.
2. **Evidence before notification.** Executor `event+cursor+continuation` is persisted and exact-read back **before** `INVOKING_CONTROLLER`; Controller successor is materialized/read back **before** the Executor resumes.
3. **Effects only while authorized.** Current `EXECUTE` grant, scope, lease/fence, actor/source/head and unpaused state are required. Read-only `PLAN` or advisory fanout never authorizes writes. Merge, separately governed Ready-for-Review, deploy, production, secrets, migration and destructive actions require distinct authority.
4. **Bounded loops.** Self-repair continues under valid `continue_until`, budget and checkpoints; semantic results trigger Controller only when a real boundary/terminal decision occurs. Avoid gratuitous chat churn.
5. **Qualified observation, no covert effects.** A deliberately registered, rate-limited **read-only** Loop mailbox observer may inspect the exact mailbox cursor for newer events. Timer-driven `/loop` prompting an LLM is not automatically a qualified cursor poller; legacy `MAILBOX_POLL` and `CONTROLLER_WAKEUP_POLL` remain forbidden. Push-first or qualified read-only pull are delivery options. No Slack machine fallback, browser scraping, hidden execution, repeated Preview messages or automatic strategy switch. Cursor discovery never grants permission to resume effects.
6. **No infinite unowned wait.** Every Controller invocation either produces a validated successor, remains explicitly pending with a durable owner/correlation/approved transport, resolves to an actionable Human wait, or fails with a recorded blocker. Pending state is not a success claim.
7. **No self-issued authority.** Neither peer consensus, Pattern E/MoA, a GPT chat reply, nor an Executor role-switch can mint approval, lease, fencing, Controller identity or a valid canonical event. Existing delegated scope is reusable without a new AI permission request.

## 3. Common Executor lifecycle and single branching point

### GPT ↔ Hermes Local forward-progress and source-sync handshake

Both autonomous peers must keep making testable progress without supervisor/subordinate gating. Every meaningful exchange includes `RUN / REPO / BRANCH / REMOTE_HEAD / LOCAL_BASE+HEAD / PATHS / TESTS / WRITER / NEXT`. Hermes Local must **fetch + reconcile** remote GPT changes before relying on them and **commit/push** its changes for GPT to consume; chat acknowledgement or local unpushed commits cannot count as code synchronization. Before overlapping edits, agree on one writer and worktree; when source moves, compare ancestry, diff and tests, then merge back published/evidence-bearing branches additively or rebase only unpublished disposable local work. Never force-push immutable evidence.

A blocked TaskController successor/expired lease pauses only the protected effect; native GWC Q0 testing and fixes continue in existing allowed scope. Qualified push and observer polling deliver deduped pointers; observed cursor is not consumed cursor and an unchanged cursor does not invoke an LLM turn. For mutual stagnation, each peer challenges assumptions, tries a safe bounded recovery option and escalates only a concrete remaining shared blocker with evidence, owner and executable NEXT. Do not issue repeated WAIT messages with no material state change.

### GWC v2 testing: frequent code drift is routine, not an automatic hold

When GWC Universal V2 is in active E2E/TDD qualification, frequent defect findings, source updates and evolving PR heads are **expected**. An additive in-scope commit is **not** by itself a new Human approval requirement, run-level `RUN_HOLD`, reason to cancel the Executor mission, or instruction to wait for GPT. The active peer should exact-read changed refs and ancestry, review diffs, update or merge back isolated branches, rerun affected validation, and continue autonomous RED→FIX→GREEN→reload→replay. A **rebase is suitable for an unpublished disposable local branch only**; for published Q0 branches or evidence-bearing commits preserve immutable SHAs and reconcile with an additive merge (no force-push, amend or silent history rewrite). Respect single-writer worktree ownership.

The **specific** exact-SHA-sensitive TaskController effects still require a current source/plan/approval/lease binding, immutable replan when needed, and load-proof regeneration when runtime binaries/modules/instructions changed. This binds the protected action only, not unrelated Q0-native development already granted by the current GWC branch authority. Use peer reasoning to resolve routine conflicts and retest, not a blanket STOP/WAIT cycle. Escalate only a genuine unsatisfied authority/scope boundary or shared deadlock after bounded recovery attempts.

### A2A continuous execution, qualified tick and deadlock-unlock contract (SCRUM-840)

**Normative controller boundary for continuous GPT ↔ Hermes coordination.** This section owns the practical wake/escalation decision, and [TaskController Mailbox v2](TASKCONTROLLER_MAILBOX_V2.md) owns human-readable message encoding. This is a host contract, not proof that Desktop has loaded an implementation.

- **Observe each qualified tick:** the registered `MAILBOX_OBSERVER` reads the bounded, exact Controller **and** Executor event cursors and the durable continuation relevant to the current run. Verify run, session, actor, pause state, provider read rate and source-bound identity. On a changed cursor, exact-read its typed event and continuation before making a decision. Keep **observed** high-water marks distinct from **consumed** seq and notification delivery receipts. Never advance an event or issue effect authority by observing it.
- **Consume / execute:** a valid new Controller command addressed to Hermes is consumed by the admitted Executor after PRECHECK; its authorized task continues. An active `ENGINEERING_WORK` mission runs independently, even without a cursor change. Intermediate test/commit/progress events do not wake GPT. Cursor unchanged with no independently runnable mission is a silent no-op: no LLM invocation, expensive test rerun, or controller wake.
- **Normal Controller wake — TERMINAL:** after a task has a verified terminal completion receipt and exact mailbox/cursor/continuation readback, deliver **one** deduplicated, pointer-only wake to the qualified bound Controller adapter. A tick ending, test passing, a new HEAD or a nonterminal progress report is not completion.
- **Exceptional Controller wake — DEADLOCK_UNLOCK:** the Executor may request a Controller decision **before terminal completion** only when a *qualified bounded engineering work cycle* has (i) re-read live evidence and runnable frontier, (ii) tried at least one concrete lawful recovery/alternate, (iii) recorded no meaningful progress or different legal NEXT, and (iv) proved that the remaining blocker belongs to Controller authority, external provider admission or a genuinely non-delegable dependency. Ordinary RED/GREEN failures, a missing fixture with remaining searchable sources, an unchanged cursor, repeated tests or a timer count are **not** deadlock.
- **One deadlock → one escalation:** persist a structured `DEADLOCK_ESCALATION` handoff with run/task/node, exact HEAD and cursor, last progress, failed recovery attempts, blocker class and owner, two or three legal alternatives, requested Controller action and smallest release condition. The idempotency key includes `run + task + last_consumed_communication_seq + blocker_fingerprint`. Preserve the task as `BLOCKED_PENDING_CONTROLLER`, **not** SUCCESS or TERMINAL. Only one pointer-only Controller wake per unchanged key; push and observer delivery deduplicate. If GPT is verified BUSY, retain one pending correlation and defer duplicate invocation; re-evaluate on verified delivery/completion or changed evidence, not every timer tick.
- **Unlock / resume:** the Controller supplies a source-bound authorized NEXT/decision or records a genuine Human boundary. Hermes exact-consumes it, checks relevant authority, and **resumes the same task**, preserving progress and evidence. If delivery fails, preserve one pending escalation and diagnose transport without manufacturing another identical report or stopping unrelated authorized work. A genuinely unresolvable terminal blocker is reported as such only after lawful recovery alternatives are exhausted.
- **Real holds:** a verified explicit user pause or `RUN_HOLD` remains binding. This contract forbids *artificial* global pauses and ACK/progress ping-pong; it does not bypass safety or grant new authority.
- **Separate channels:** an A2A communication comment may describe an escalation but is neither the canonical C/E event nor proof the Controller was woken. Actual dispatch requires the qualified host adapter, current typed evidence and receipt.

**Required verification matrix:** (1) qualified tick observes C/E, unchanged cursor → no turn; (2) new Controller command → Executor consumes; (3) intermediate Executor progress → no GPT wake; (4) lawful alternate remains → recover locally; (5) one bounded no-progress work cycle + Controller-owned blocker → one early unlock request; (6) same deadlock across multiple ticks/restarts and push+observer → one correlated wake; (7) GPT_BUSY → pending only; (8) successful Controller unlock → same task resumes; (9) terminal result → one final wake; (10) invalid run/digest/actor and actual RUN_HOLD → fail closed. Tests and a live adapter receipt, not this prose alone, are required for E2E PASS.

### Loop observation versus LLM-led execution

The Loop has **two independently authorized concerns**: `MAILBOX_OBSERVER` may perform a bounded, read-only cursor check; `ENGINEERING_WORK` may advance an already-authorized mission with LLM reasoning. Neither is equivalent to calling `LoopManager.resume()` or unconditionally firing native ticks.

- **READ:** qualify `loop_run_id == canonical_run_id`, single session owner, exact mailbox ref, bounded interval, minimum cursor, GitHub read scope/rate budget, absence of user pause or RUN_HOLD. Detect a newer cursor, then exact-read the typed event, immutable continuation and source; never scan all issue comments as authority.
- **DECIDE:** use LLM reasoning for material new events and independently executable engineering choices, **never for a raw unchanged observer cursor alone**. Duplicate/stale observations are silent no-ops and do not count as failed work cycles. Keep observation high-water mark separate from consumed command sequence and confirmed delivery ACK.
- **EXECUTE:** every effect still requires a current mission grant, source/scope/boundary, recipient identity, current issuer-owned lease/fence and PRECHECK. `EFFECT_HOLD` may permit the qualified read-only observer but forbids denied effects. `RUN_HOLD` and explicit user pause stop this run's observer/turn.
- **CONTINUE:** while a valid delegated mission is active, Hermes may reason, implement, test and fix autonomously; GPT may independently propose/challenge through the bound communication plane. Escalate *real* scope/authority changes, not a routine red test.
- **DELIVER:** event-push and qualified read-only polling may converge to one deduplicated pointer/turn. There must be no two active effect writers or duplicate turn execution. The adapter must prove the session's authenticated `agent_instance`; the Desktop `Bot Chat` capability flag alone does not.
- **QUALIFY HOST, DO NOT ASSUME:** Hermes fork branches may implement hybrid event/observer behavior, but a pushed commit does not prove the active Desktop process loaded that build, bound the current session, registered the observer, or can deliver a command. Verify host source SHA and live adapter before claiming E2E. This runbook alone never installs an observer, changes Loop.route, resumes a paused Loop or mutates #595.

```text
Recover exact run + selected controller_strategy
  → BOOT → PRECHECK
  → EXECUTING (/goal) ↔ VERIFYING (test / fix)
  → REPORTING (typed Executor mailbox event + cursor exact-readback)
  → INVOKE_CONTROLLER(executor_event_ref, bound strategy)   ← ONLY BRANCH
  → wait for / receive valid Controller event reference
  → CONSUMING_CONTROLLER → PRECHECK
  → EXECUTING again | AUTHORITY_WAIT | BLOCKED | TERMINAL
```

Conceptual adapter interface (design contract, **not** a deployed SDK):

```text
invoke_controller(
    executor_event_ref,
    controller_strategy,
    actor_binding,
    continuation_ref
) -> CONTROLLER_EVENT_REF | PENDING(correlation, owner, recovery_ref)
   | AUTHORITY_WAIT(actionable_request_ref) | BLOCKED(reason, evidence_ref)
```

The returned `CONTROLLER_EVENT_REF` is **only a pointer**. The main Executor never executes from adapter prose: it must exact-read and validate the actual typed Controller event and durable continuation.

## 4. Controller invocation — two strategies

### A. `standalone`: internal Controller phase + Pattern E → MoA

1. Main Executor **quiesces all effects** and reports exact typed `executor_event_ref`; capture the observed event/cursor/continuation.
2. Switch *operating phase* inside the same Hermes Desktop main session **only if this host is independently admitted as canonical Controller** for this run; Controller and Executor mailbox writes must remain distinct and serialized. A previously GPT-bound run cannot silently switch actors.
3. Controller exact-consumes the Executor event. If specialist analysis is needed and allowed, consult [Pattern E — SlackFanout](https://github.com/nhatnguyenquang1838-coder/hermes-sync/blob/67e332fb2ef3d2cd0e86e0b8f1a20fcf3d235bb6/skills/dwa-a2a-coordination/SKILL.md): `~/.hermes/dw_superapps/fanout.py` fans a scoped task to specialist Bot Chat sessions; optional `/moa` synthesizes **advisory** recommendations. Verify exact repo/SHA/evidence independently. The original script is Slack-ingress oriented; in-session adaptation and installed tool availability remain **unqualified** until on-host E2E.
4. Controller applies **canonical** TaskController gate/admission/Human authority checks and selects one legal next decision. Pattern E does **not** approve effects, extend leases, alter scope or create machine events.
5. If allowed, persist continuation, append typed Controller successor and cursor using runtime-owned components; exact-readback. If Human authority is needed, record an actionable Human request and enter `AUTHORITY_WAIT` without inventing approval.
6. Hand back **only** verified Controller event reference to the main Executor. Revalidate entire PRECHECK before resuming the native goal. If Controller binding/materializer/fanout provider fails, return a truthful blocker; do not call GPT Web or Slack as fallback.

**Source caveat:** The external Pattern E skill includes historic v1 mutable mailbox and Slack/polling instructions; current DW-SuperApps mailbox/v2 + event-driven contracts **take precedence**. Specialist Bot Chat calls are not TaskController child runs under `max_children=0`. The separate Controller-advisory permission must be established; this runbook does not supply it.

### GPT liveness / bounded no-progress decision (GPT_BUSY vs GPT_IDLE)

**Scope:** This table applies when an existing communication/executor work cycle needs the GPT peer, not to every raw read-only mailbox observation. Treat independently authorized engineering as runnable even when a legacy machine-effect binding is stale. Resolve GPT state from a **qualified host/session signal**; a delayed comment, missing preview, unchanged seq or an assumption that GPT is reading is not evidence of `GPT_BUSY` or `GPT_IDLE`.

| Evidence / current state | Action now | Next wake or escalation |
| --- | --- | --- |
| **`GPT_BUSY` verified** (an active GPT turn or transport-in-flight with exact correlation) | **Fail-fast the *new GPT invocation***: do not open another GPT turn, resend the same ask, or busy-poll. Persist one pending correlation once, then continue legal local source recovery/tests or yield. | On genuine completion/event/timeout evidence, inspect correlation and consume once. An unchanged observer cursor is a silent no-op. |
| **`GPT_IDLE` verified + valid local NEXT exists** | Execute the independently authorized NEXT, test/fix/reconcile, publish evidence. | Report on meaningful change; no idle escalation yet. |
| **`GPT_IDLE` verified + no legal NEXT + *completed bounded work cycle* without progress** | Perform one bounded reality check: latest v2 communication seq, current remote/source, pending correlation, attempted recovery and whether a peer already owns the blocker. | **Escalate exactly once per unchanged stall key** (`run + relevant last consumed communication seq + blocker fingerprint`) via v2 `REPORT` with evidence, last progress, owner, 2–3 legal alternatives and smallest release trigger. Do not create another identical report on each tick; re-evaluate only on a changed command, evidence, owner or release trigger. |
| **`GPT_STATE_UNVERIFIED` / unavailable transport** | Do not infer busy or idle. Keep available native work moving; perform bounded recipient/adapter diagnostics. | If no lawful progress after bounded attempts, emit one actionable transport blocker, not repeated generic WAIT. |
| **Observer cursor unchanged** (raw cheap read) | Silent no-op; **no LLM turn, no retry and no escalation merely due to polling**. | A real work-cycle completion or an event/qualified wake may separately trigger liveness evaluation. |
| **User pause / `RUN_HOLD`** | Respect the pause according to its verified scope. | No automatic rearm or resume from a timer or a communication comment. |

**What counts as a completed no-progress work cycle:** a qualified work invocation was actually admitted, examined current evidence and attempted bounded lawful NEXT/recovery, but produced no changed artifact, test/evidence receipt, actionable decision or valid next action. A timer tick, raw cursor inspection, silent no-op, or a GPT busy signal alone does **not** qualify. Persist a concise stall fingerprint and prior escalation pointer to dedupe across Loop restarts. `GPT_BUSY` is fail-fast for repeated *GPT calls*, **not** an instruction to cancel the engineering mission.

**Obsolete Loop route:** `ROUTE_BINDING_MISMATCH` quarantines only the mismatched scheduler row and any effect dependent on it. Do not rewrite an obsolete run's stored route to the current run. A fresh/current native engineering session can continue within source-authorized scope while the host registers a separately verified current-run observer/Loop. Do not resume the old row solely to deliver a v2 communication. The current [Mailbox v2 Runbook](TASKCONTROLLER_MAILBOX_V2.md) owns envelope format and communication seq; do not require old machine C/E successor or lease merely to report a finding.

#### Clean host Loop instruction (reference; replace obsolete 652-run prompt only after host readback)

```text
Hermes continuous Q0 peer. On a qualified wake, read DW-SuperApps AGENTS.md,
docs/runbooks/TASKCONTROLLER_MAILBOX_V2.md and HERMES_DESKTOP_RUNTIME.md.
Resolve the exact current Q0 run and last v2 communication COMMAND/REPORT.
Read source/branch HEAD, keep local and remote code in sync, then THINK,
reproduce RED, fix, test GREEN, reload/replay within existing delegated scope.
Use human-readable v2 communication seq+1 for material REPORT/ACK.
Cheap observer read with unchanged cursor: silent no-op, no LLM turn.
Verified GPT_BUSY: fail-fast duplicate GPT invocation, keep one pending
correlation; continue other legal work. Verified GPT_IDLE and one genuine
bounded no-progress work cycle with no local NEXT: escalate once with exact
evidence, blocker owner, recovery choices and release trigger.
Do not mistake an obsolete ROUTE_BINDING_MISMATCH Loop for a run-level hold,
and do not auto-resume, rebind or replay that obsolete scheduler row.
Respect explicit user pause and GWC/project effect authority.
```

### B. `coordination`: GPT Web Controller via in-app-browser / Drive Preview

1. Main Executor first writes and **exact-readbacks** typed Executor mailbox event/cursor, then uses the **qualified and bound** Hermes in-app-browser / `drive_preview` to send a **pointer-only** message to the exact GPT Web Controller thread:

```text
TASKCONTROLLER_EXECUTOR_EVENT_READY
run_id: <canonical run ID>
executor_mailbox_ref: <exact event reference>
executor_seq: <new sequence>
event_digest: <observed digest>
action: Exact-read Executor event; return Controller successor event reference.
```

2. **GPT Web Controller** exact-reads Executor event/evidence with its authorized GitHub access, evaluates the decision and any required Human approval, persists canonical continuation, publishes typed Controller event/cursor via the approved runtime and exact-readbacks it. GPT prose `APPROVED` is **not** authority.
3. The **admitted** Preview response/delivery mechanism signals the successor pointer back to Hermes (or a separately approved event adapter delivers it). Hermes must distinguish transport notification from actual GPT mailbox **consumption**. Do not assume reply delivery, automatic wakeup, or an installed `drive_preview` API without evidence.
4. Main Executor exact-reads the successor Controller event and returns to PRECHECK. If Preview is missing/unbound or GPT cannot consume, mark the affected protected delivery `TRANSPORT_BLOCKED`; use an independently qualified push adapter or bounded read-only `MAILBOX_OBSERVER` for discovery if admitted. Do not use unqualified browser/Slack substitutions or infer effect authority from observing a cursor. Continue independently authorized engineering, test, code sync and peer discussion.
5. `WAITING_CONTROLLER` is allowed only with a durable pending correlation, real owner and approved return signal. Apply the **GPT_BUSY versus GPT_IDLE** liveness decision table below; no busy-loop, duplicate send or unbounded repeated GPT calls.

**Contract caveat:** Current [Controller registry](../../controllers/taskcontroller.yaml) requires event-driven mailbox/v2; `hermes-cloud` declares `mailbox-event`. Neither this registry nor this runbook qualifies Hermes **Desktop** Preview as a live notification binding. A separate approved binding/adapter validation is required before real execution in this mode.

## 5. Event-to-event continuity matrix

| Scenario | Shared Runtime | Standalone invocation | Coordination invocation |
| --- | --- | --- | --- |
| Normal TDD failure within scope | Stay `EXECUTING` → repair → verify | **No** Controller call | **No** GPT/Preview call |
| Controller decision genuinely needed | Publish Executor event → `INVOKING_CONTROLLER` | Internal Controller phase; optional Pattern E/MoA; canonical successor | Preview pointer to GPT Web; canonical successor |
| No specialist advice needed | Reuse same reporting/consume path | Controller can decide from evidence without fanout | GPT can decide from evidence |
| Human approval required | `AUTHORITY_WAIT` with actionable request, no effects | Internal Controller asks Human legitimately | GPT Controller asks Human legitimately |
| Adapter unavailable | `BLOCKED`, preserve exact evidence | No impersonated Controller or fake fanout | No browser/Slack/polling fallback |
| Verified `GPT_BUSY` | Fail-fast this invocation without repeated sends; retain one pending correlation and continue other work | No overlapping in-session turns | Preview ACK does not imply GPT consumed; never spam |
| Verified `GPT_IDLE` + no local NEXT after bounded work cycle | One evidence-backed escalation per unchanged stall key, not a poll-triggered LLM turn | Escalate shared no-progress once | Report exact last-seq, attempted recovery, owner, release trigger and options |
| Observer mailbox unchanged (raw poll) | Silent no-op; do not count a work cycle or trigger escalation | Same | Same |
| Duplicate/stale notification | Dedupe by bound event identity; no re-execution | Reject stale Controller actor/seq | Reject stale GPT reply/event |
| New valid Controller event | `CONSUMING_CONTROLLER` → full PRECHECK | Same Desktop main Executor resumes | Desktop Executor resumes |
| Expired lease / user pause | `PAUSED/BLOCKED`; do not resume | No local self-renewal | No GPT prose bypass |
| Verified mission completion | Typed Executor result then Controller terminal disposition | Internal Controller verifies | GPT Controller verifies |

## 6. Recovery and migration guard

- Resume from **exact** current event/cursor, durable continuation, actor, attempt, lease/fence, branch/head/CI and relevant evidence, never from prior ChatGPT messages, Slack history, Loop ticks or uncommitted local notes.
- Do not mix `dw.taskcontroller.a2a/v1` mutable comments with canonical `dw.taskcontroller.mailbox/v2` append-only typed events. Runtime-owned materializers control sequences/digests.
- For an expired authority or stale fence, the Controller must perform the legal recovery transition and issue a *new* valid event. No automatic `/goal resume`.

  **Controller-host recovery entrypoint (one-shot, not an Executor command):**
  `scripts/taskcontroller_mailbox_recover.py` invokes the canonical
  `recover_high_integrity_session()` with a pinned head SHA and GitHub-backed
  mailbox/continuation stores. Run only under a **separately admitted Controller**
  identity with its existing host-provided `GITHUB_TOKEN`, after validating any
  `RUN_HOLD` restrictions. For the selected run, resolve `--repository`, `--issue`, `--run-id` and `--expected-head-sha` from the live canonical Controller mailbox/continuation. Do not boot the old hard-coded SCRUM-781 issue/run as a default.

  A successful run yields immutable **continuation recovery evidence only**:
  `WAIT_CONTROLLER / RESOLVE_EXECUTION_AUTHORITY`. It does **not** grant G2,
  advance Controller mailbox event/cursor, notify Hermes, or resume T1–T7.
  Afterward, resolve route-specific authority and produce a fresh typed
  execution request with `scripts/taskcontroller_mailbox_materialize.py`
  (again using the admitted Controller runtime), exact-readback, and only then
  deliver via an independently qualified Coordination notification adapter.
  Never use a legacy `APPROVE G2` token as a Universal V2 cursor release.

- Historical E9/E5, expired leases, Loop ticks and `last_stop_reason` values are audit references only. Do not attribute a pause/resume to a user without an actor-bearing event. Reconcile the *current* canonical run from exact mailbox/continuation refs rather than an older host Loop. Never replay an expired command or auto-unpause an obsolete Loop.
- Do not conflate a local provider capability demonstration with a passed governed TaskController E2E or runtime readiness.

## 7. Acceptance criteria and test matrix

### Static contract checks

- [ ] Root + Hermes + agent-index routing point to **this single runbook**; obsolete two-mode runbooks are absent.
- [ ] One shared state machine and Executor execution lifecycle; strategy selection occurs only at `INVOKING_CONTROLLER`.
- [ ] Contract binds strategy, actors, mode-specific transport and no implicit fallback; `max_children=0` is **not** a mode selector.
- [ ] Every Executor event and Controller successor has durable typed mailbox/cursor/continuation readback; identity, digest, source, lease/fence, pause and exact-head guards remain intact.
- [ ] No approval/lease invented from peer consensus, MoA or GPT response, and no **unqualified** periodic mailbox/Preview polling.
- [ ] TaskController mailbox/v2 remains the canonical machine state; legacy unqualified polling and wakeups are forbidden; an explicitly qualified read-only Loop observer may inspect a bounded exact cursor (no effect authority), and exact wakeup fields come from the live source chain.
- [ ] Host Goal/Loop/Heartbeat controls do not grant TaskController/GWC lifecycle authority; no local Task TodoList or generic RunState schema is invented.
- [ ] GPT browser transport is used only through an explicitly qualified binding and the existing `dwa-gpt-exchange` procedure.
- [ ] Settlement requires a confirmed real firing with `awaiting_response=true`, one exact-owner `complete_tick`, and fresh readback showing the expected post-state; `false` alone is not historical proof.
- [ ] A Goal/Loop binding pins this runbook's exact commit SHA at bind time; no implicit tracking of a moving `main`.

### Live provider checks (not satisfied by documentation)

1. **Standalone — happy path:** same main session, separately admitted Controller actor, bounded Pattern E/MoA, typed Controller successor, Executor consume and continuation.
2. **Standalone — real boundary:** Human authority request stops mutation; Controller phase cannot self-grant/extend a token or act as concurrent Executor writer.
3. **Coordination — full round trip:** typed Executor result → readback → verified bound `drive_preview` → GPT **exact** consume → valid typed Controller successor → observed return pointer → Hermes re-PRECHECK.
4. **Coordination — missing preview/tool:** deterministic `TRANSPORT_BLOCKED` with persisted evidence and no fallback.
5. **Both — TDD liveness:** multiple in-scope failures repaired without Controller chat turn or `/loop`.
6. **Both — retries:** duplicate/late notifications, repeated cursor observations, expired lease, stale fence and user pause cause **zero repeated effects**.
7. **Both — terminal:** verifiable exact-head tests/artifacts and canonical Controller terminal disposition; no optimistic success from UI/session stop reason.

**Additional SCRUM-840 checks:** (i) both peer-order permutations give the same decision; (ii) consensus without effect authority does not issue a grant; (iii) legacy polling remains paused; (iv) qualified read-only observation on unchanged cursor emits no turn; (v) wrong run, user pause, RUN_HOLD and duplicate event block execution; (vi) a Desktop loop/observer E2E proves the real recipient binding before delivery.

**Readiness:** Until provider bindings and live tests pass, report **DOCUMENTED / E2E_UNVERIFIED**, not `RUNTIME_READY`.

## Hermes host Loop integration boundary (generic)

This repository runbook governs Desktop runtime/provider behavior and its TaskController integration. It is not a second Hermes host-scheduler manual or TaskController/GWC contract. Use the local `hermes-loop-operations` skill for native Goal/Loop/Heartbeat mechanics and `dwa-gpt-exchange` for GPT browser transport; both are procedure aids subordinate to the live DW-SuperApps and applicable GWC source chains.

- **Host-control ownership:** `GoalManager`, `LoopManager`, and `HeartbeatManager` control only their respective native scheduler rows. They do not grant repository, mailbox, gate, or human authority.
- **Source-owned lifecycle:** use the active project's declared lifecycle state/cursor and typed `NEXT`. This runbook does not define a universal `RunState`, `RuntimePlan`, `Task TodoList`, `DONE`/predecessor rule, or `validity_key`. Do not invent local C/E cursor or deadlock predicates; follow the exact current protocol records.
- **Mailbox observation boundary:** task communication follows `docs/runbooks/TASKCONTROLLER_MAILBOX_V2.md`; existing typed machine records remain immutable. A verified `MAILBOX_OBSERVER` may perform bounded read-only observation without issuing a command, advancing consumed seq or turning every unchanged poll into an LLM turn. Legacy unqualified `MAILBOX_POLL`, browser scraping, or arbitrary timer-driven GPT prompt is not automatically admitted. Classify each Loop's actual bound run, host/session and adapter first; an obsolete paused scheduler row does NOT stop the current Executor session or separately authorized Q0 engineering. Do not relabel old `ROUTE_BINDING_MISMATCH` as a global Q0 hold, silently rebind old routes, auto-unpause or replay expired attempts. The live host's observer support must be verified on its exact loaded build; no unrestricted polling or inferred permission.
- **Expired lease/fence:** recovery remains Controller-owned. The Executor must not renew a lease/fence, invoke recovery/materialization, or create a successor event/cursor. A recovery receipt alone is not a typed execution grant.
- **Browser transport:** only use a GPT browser route when the active strategy/registry binds a qualified adapter and exact conversation. Otherwise keep `TRANSPORT_BLOCKED`; do not use a fallback or infer delivery from UI output. The exact stage/submit/readback flow belongs to `dwa-gpt-exchange`.
- **Optional advisory analysis:** if an active contract requests one MoA review of a source-bound deadlock fact block, it is advisory only; empty/partial/provider-failed output is `INCONCLUSIVE`. It cannot create a mailbox event, grant authority, decide a source-owned cursor predicate, or perform lease recovery.
- **Loop continuity:** first evaluate the pure `taskcontroller.controlplane.orchestration_policy.decide_executor_loop_continuity()` guard using the live run/Loop binding, hold type, validated EXECUTE contract and event adapter. `scheduler_action` refers only to the host row; `executor_session_action` and `typed_next` separately identify persistent Executor/session status and current owner. The guard does not call `LoopManager.pause()` or `resume()`, grant authority, or create an event. A Loop bound to a different run is quarantined, not adopted/restarted.
- **Loop settlement:** for a confirmed real firing only, exact-read the same owner/session and create/verify the required pre-settlement backup. Call `LoopManager(session_id).complete_tick(last_response)` exactly once only when that firing has `awaiting_response=true`; then use a fresh manager readback to verify the same firing and `awaiting_response=false` as the postcondition. A paused Loop or pre-settlement `false` means no current firing to settle and does not prove historical settlement. Never replay, backfill, or synthesize a tick or backup.
- **Binding:** when a native Goal/Loop contract explicitly binds this runbook, record its exact repo commit SHA at binding time and keep that revision fixed for the run. Do not silently follow moving `main`; a document change does not mutate native manager state or rebind a live run.
