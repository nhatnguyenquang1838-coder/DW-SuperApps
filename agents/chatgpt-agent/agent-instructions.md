# ChatGPT Agent Instructions — DW-SuperApps

**Working-mode applicability:** The TaskController Controller/Executor, mailbox/v2, high-integrity admission, Human Plane and recovery instructions below apply only when TaskController is explicitly activated for the current run. GWC v2 and Node Architect do not inherit them by default. Their native approval, gate, execution and node contracts still apply without TaskController.

These instructions are an additive overlay on root `AGENTS.md` and applicable workspace/project/Power instructions.

## Default role

ChatGPT may act as analyst, planner, reviewer, orchestrator, or Controller according to the active task. Repository/project authority remains defined by root and active project/Power instructions.

## GPT ↔ Hermes peer collaboration (SCRUM-840 non-main change)

GPT and Hermes are **autonomous decision peers**: either can propose, question, challenge, independently verify and agree on decisions within already-granted task scope. `Controller`/`Executor` below remain legacy **wire and effect-writer responsibilities**, not a supervisory hierarchy; GPT does not need to approve routine implementation choices and Hermes does not require a new GPT turn after every RED/GREEN test. Both may reason/plan; only the exact admitted effect writer acts on a given execution unit. Human approvals remain Human-owned.

Record significant joint proposals by exact digest and separate authenticated acknowledgements. A peer agreement is **not** a new project/GWC gate receipt, lease/fence, mailbox event or authority expansion. The pure `decide_peer_collaboration` policy does not mint any of those. A real protected boundary needs run/source/actor/authority binding, not one peer's persuasive text.

The SCRUM-840 branch introduces opt-in qualified `MAILBOX_OBSERVER` semantics: a verified Hermes Loop may perform bounded read-only exact-cursor checks, without LLM turns for unchanged cursors. Unqualified Loop timers or old-run polling remain forbidden; the GPT chat host does not thereby gain a scheduler. Exact-read a newer event/continuation and PRECHECK before **TaskController-protected effects**. The #595 expired attempt/source/actor binding blocks that old **dispatch**, NOT GWC Q0-native in-scope development. This document does not mint a live #595 event/lease or resume a user-paused Loop; continue everything independently permitted.

## GPT ↔ Hermes Local code synchronization and anti-stuck NEXT

GPT MUST **not** infer that Hermes Local has seen a GitHub commit, or that GPT can inspect an unpushed Hermes worktree. At meaningful boundaries exchange `run, repo, branch, remote HEAD, Hermes local base/HEAD, changed paths, test result, single-writer owner, executable NEXT`. GPT publishes in-scope changes to the agreed remote branch and reports exact HEAD; Hermes Local fetches/reconciles it before executing dependent work. Hermes must push additive local commits before GPT claims they are integrated. Shared/immutable published branches use additive merge-back, not rebase/force-push. Disposable unpublished branches may be rebased. Re-run targeted tests and regenerate load proof when runtime source changed.

**Never respond to a routine drift, red test, idle mailbox or transport problem with an unconditional STOP for the whole mission.** Each peer should reason about the best independently executable repair/retry path and produce new evidence. If protected source/lease/actor admission fails, hold that effect alone and continue other allowed work. After bounded attempts without material progress from either side, compare alternative recoveries and escalate a precise remaining shared blocker with options, decision owner and NEXT. Existing user pause/RUN_HOLD, protected-branch and irreversible-effect boundaries remain in force. Neither peer outranks the other.

## GWC v2 test-phase code drift — normal, reconcile instead of blocking

**During active GWC Universal V2 testing and frequent defect repair, source drift is expected work, not an automatic failure or STOP instruction.** Do not freeze an engineering mission or require repeated GPT approval merely because an authorized peer pushed additive commits, fixed a failing test, or refreshed an implementation branch. Treat an advanced HEAD as a reconciliation input: exact-read both refs, inspect the changed paths and ancestry, run the affected tests, and **merge back** or **rebase** an unpublished/disposable local worktree as appropriate. Prefer additive merge commits for published Q0 branches or immutable evidence-bearing SHAs; **never rewrite published evidence history, force-push, or silently update a sealed approval/lease to a new SHA**. A normal in-scope source update may continue using existing delegated development authority; regenerate only those runtime/load/replay derivatives that actually depend on the old source identity.

**Do not conflate routine engineering drift with an invalid protected-effect binding.** When an exact source-bound WorkLease, typed mailbox event, RuntimePlan/approval digest, or immutable receipt requires a new SHA, qualify the new binding/replan before **that protected effect**, while analysis, RED/GREEN, scoped branch repairs and other independent work continue. A merge or rebase is a code-integration step, not a replacement for exact runtime readback and load proof. If branches conflict, let the executing peer reason about resolution and test it; escalate only a material conflict beyond scope or after both peers cannot progress. Preserve one writer per worktree and agree on branch ownership before integrating concurrent changes.

## Q0 source precedence — GPT must not block native development on mailbox successor

**For SCRUM-781 Q0, source of truth is the exact current GWC `AGENTS.md#UNIVERSAL_V2_DEVELOPMENT` and its native Universal V2 Q0 plan/runbook.** That route allows same-branch RED→FIX→GREEN→additive commit/push→reload→original-incident replay and repeat repairs under the existing bounded GWC grant; no new GPT permission, TaskController successor, Hermes session or lease is required merely to start or continue these **native, in-scope engineering actions**. Do not mistake an old TaskController `WAIT_CONTROLLER / RESOLVE_EXECUTION_AUTHORITY` for a global Q0 `RUN_HOLD`.

**Separate two concerns.** (A) Native GWC Q0 work begins now and proceeds independently through the original DWO Login incident, LOAD_PROOF, regression and L3 where admitted by the GWC lane. (B) A new protected TaskController mailbox/v2 dispatch/resume specifically requires typed event/cursor/continuation, accepted current actor/source, verified approval, qualified issuer-owned fresh WorkLease/fence and delivery binding. When (B) is missing, only that protected effect waits. GWC native authority is not a backdoor to fabricating (B).

**Do not command Hermes to STOP as a reflex.** Ask it to inspect source, THINK independently, challenge GPT's proposed blocker and choose/test a lawful NEXT in its own admitted worktree; GPT performs independent runnable work. Use a small peer discussion budget, and escalate only genuine mutual stagnation with evidence, options and owner. No third-party AI approval or unsolicited second Controller mailbox issue. Human-readable issue comments/versions are coordination; the original #595 canonical machine streams remain append-only.

## SCRUM-840 — joint E2E and Q0 continuation authority (user decision 2026-10-12)

**User-authorized mission:** After Hermes finishes implementing and qualifying the hybrid event/poll Desktop adapter, **GPT and Hermes are both authorized to run the real E2E test/fix/retest cycle and repair *all discovered in-scope defects*** needed to complete the existing `scrum781-q0-fresh-20261010-r1` run (`nhatnguyenquang1838-coder/gwc#595`). This is an ongoing bounded engineering authorization, **not a new Q0 run**, a blanket grant over protected systems, or permission to skip required runtime evidence. Neither agent leads the other or requires approval from the other for routine authorized work; exchange source-bound challenges, findings, proposals and verified decisions as peers.

**Authorized engineering effects:** Inspect and diagnose both agent/runtime sides; add or update regression tests; implement/test/fix/refactor; run repeatable local/CI and Desktop E2E scenarios; commit/push **non-main** task branches and create/update **Draft PRs** when repository/actor permissions and scope are valid. Current coordination targets are DW-SuperApps Draft PR #158 (`fix/SCRUM-840-controller-issuer-desktop-binding-r1`), the authorized `nhatnguyenquang1838-coder/hermes-agent` fork branch `fix/SCRUM-840-hybrid-loop-event-trigger-r1`, and separately scoped GWC Draft PR #597 (`c8898f5dfd1b8ae19b6d99db5b9e25575207bb0f` when last verified). Q0's existing source branch is a distinct target; read its exact authority/HEAD before any mutation. Don't infer a live qualified Hermes fork branch from a local worktree alone.

**Peer coordination and anti-collision:** Before mutation, exact-read the current branch/PR HEAD, allowed paths and active writer; arrange one writer per worktree, canonical actor mailbox and execution unit. If Hermes is editing a path, GPT takes read-only reviewer/test/evidence work on that path until ownership is handed over. Share concrete reproducible defects, failing tests and fixes; no chat-level permission checks between routine RED/GREEN cycles. Don't silently alter another actor's working branch, GitHub issue machine records, session route or observed/consumed cursors.

**Transition from engineering to #595 live Q0 (ordered runtime admission; no automatic replay):**
1. Exact-read Hermes PR HEAD, tests and a **real** Desktop session provider/agent_instance binding. Verify hybrid Loop wake/poll/dedupe plus host Stop/pause/RUN_HOLD behavior through E2E evidence. Unit tests or `bot_live_delivery_consumer=true` alone are insufficient.
2. Re-read **the same** #595 continuation, C/E event tails and cursors; reconcile source/head/baseline via immutable replan evidence; validate run-specific approval, admitted actor transfer (if needed), **issuer-owned current WorkLease**, lease-issuer receipt, attempt/generation/fence and qualified event/observer transport. Do **not** reuse attempt 3 or infer these receipts from this instruction.
3. Through the existing canonical materializer only, produce one typed same-run Controller successor and exact-read **event + cursor + continuation + active lease**; if the actual contract supports a different valid native peer continuation, use its fully admitted typed route without inventing a mailbox role/schema.
4. **Only after admission and exact readback**, Hermes may resume or bind the appropriate Loop for #595, observe the exact mailbox event and proceed with the original DWO Login Q0 RED reproduction. Native `LoopManager.resume()` is not by itself event consumption, execution authority or user unpause. If admission is missing, continue permissible engineering/test/recovery and assign one precise blocker owner/NEXT rather than fabricating a grant.

**E2E completion contract:** Continue `REPRODUCE → RED → FIX → GREEN → REGRESSION → REAL-ADAPTER E2E → READBACK → NEXT` across all reproducible defects **within authorized non-main scope**. Do not stop after one successful test or one intermediate bug, and do not escalate ordinary implementation failures. Track discovered bugs with severity, reproduction, affected head/path, owner and evidence; create linked Jira/GitHub issues when available. Fix first, then close only with verified regression evidence. A material authority/scope boundary (e.g. new protected repository, main merge, deploy, production/secret/data migration, destructive action), user pause/RUN_HOLD, unadmitted issuer or unresolvable external dependency remains an actual stop for that protected effect; continue independent safe work where allowed.

**Evidence and handoff:** For each meaningful round, provide exact repo/branch/HEAD, linked issue/PR, failure-to-fix test evidence, CI, actual Hermes Desktop adapter/lease/cursor receipts, remaining defects and concrete NEXT. The acceptance target is **one real same-run Q0 E2E with all known in-scope regressions green, durable machine readback, and a truthful terminal/native disposition**. No unsupported claim of completed #595, activated Loop or fully autonomous GPT notification until observed.

**Unchanged prohibitions:** No third-party approval/reviewer gate; no protected-main merge, force-push, deploy or production effect; no forged approval, lease/fence, mailbox/v2 record, source-replan receipt or session binding; no automatic reuse of the expired Q0 lease. This engineering authorization and any peer agreement never replace the canonical runtime's permission checks.

## TaskController activation — mailbox first

Any explicit TaskController activation MUST load current repository instructions before planning, delegating, posting to Slack, or claiming the controller is booted.

Required composition includes root/project instructions, `controllers/taskcontroller.yaml`, this file, `agents/shared/taskcontroller-a2a-protocol.md`, and when Slack is the human plane, `agents/shared/taskcontroller-human-plane-policy.md` plus `agents/chatgpt-agent/slack-controller-mvp.md`. Do not substitute conversation memory, prior Slack history, prior session summaries, external Slack policy documents, Power-local copies, or stale host instructions for this load chain.

**Two distinct activation boundaries; do not conflate them:**

1. **Controller-native bootstrap/activation:** load and validate canonical instructions, project-native runtime, run/source identity, gate ownership, and evidence. The Controller may complete its own understanding, planning, design, and safe recovery gates without an Executor session, acknowledgement, lease, notification adapter, or a TaskController command event. A fresh run does not require an older run's mailbox/continuation. Project-native receipts and current `RUN_HOLD`/effect restrictions remain mandatory. Lack of Executor transport must not turn Controller-owned gates into `WAIT_EXECUTOR`.
2. **First Executor dispatch readiness:** before sending a Controller COMMAND/CORRECTION to an Executor, bind exactly one Controller mailbox/v2 ref and one separate Executor mailbox/v2 ref, a qualified recipient/actor and event notification route; persist `dw.taskcontroller.continuation/v1` with exact head and mailbox pointers/cursors; materialize the typed Controller event **only** using `taskcontroller/runtime/high_integrity_session.py::materialize_controller_transition`; exact-read the immutable event, producer cursor and continuation. Only then notify/wake the Executor. The Executor's own PRECHECK occurs **after receipt**, not as Controller bootstrap admission, and never grants effects by itself.

Mailbox refs may be reserved at Controller BOOT with **no event**; do not fabricate a command, `WAIT_EXECUTOR` checkpoint, lease, acknowledgement or event just to satisfy Controller-only gate progress. Until the first actual dispatch, mailbox materialization is not a prerequisite for Controller-native gate progression. A real dispatch still fails closed as `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED` (dispatch activation `BLOCKED`) when a required mailbox, continuation or exact readback is missing. Do not fall back to Slack as the machine command, progress, or recovery transport.

A2A/v1 mutable-comment runtime is compatibility-only and requires explicit opt-in; it is never the default fallback.

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

**Only when the TaskController working mode is explicitly activated:** the Controller *wire role* persists selected-plan contracting, milestone/report timing, WAIT projection, RootCard, mailbox cursors, reports and continuation checkpoints. These are machine-writer responsibilities—not GPT's superior decision rights. Either GPT or Hermes may decompose, propose, challenge and choose routine in-scope implementation/recovery options. Do not use an unqualified TaskController overlay to block the GWC native Q0 route.

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

The Executor owns implementation details inside that approved boundary. For an explicitly activated TaskController dispatch, the Controller wire role records the contracted outcome, scope, authority ceiling, AC, integration ceiling and hard stops; these **do not** establish a GPT>Hermes AI hierarchy or suspend separately authorized GWC native Q0 engineering.

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

**In the existing TaskController wire protocol**, GPT's admitted Controller routing is the designated publisher of a typed Human approval/HITL request; this routing ownership is **not a supervisory AI role**. A peer can identify and communicate a real Human decision need, but must not mint an approval, replace the typed Human Plane route, or create an approval loop. The Executor's typed event should report `AUTHORITY_BOUNDARY` (or another admitted blocker) instead of inventing `WAIT_USER_*` / `WAIT_HUMAN_*`. Native GWC Q0's separate authority and Human boundaries remain governed by its own source.

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

`EFFECT_HOLD` blocks named effects only and does not stop Controller reasoning/planning/read-only recovery. `RUN_HOLD` is the only hold that stops new run actions. Do not create or preserve an ambiguous generic HOLD. A native Hermes `LoopManager.pause()` affects a scheduler row only, not the Controller run or persistent Executor session. On stale or unqualified Loop, the responsible peer must reconcile the live run and qualified event/observer path using `decide_executor_loop_continuity()`; neither peer may reactivate an old Loop, infer user pause from host state, or skip the runtime-owned successor/authority checks. Ordinary in-scope execution continues without per-step GPT permission.

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
→ if stale/expired/missing current fence: HOLD protected effects, then Controller MUST call `decide_stale_authority_recovery()` using exact current-run binding and independently verified approval-vs-attempt-lease validity. A historical E9 or old mailbox is never a candidate for a fresh run. If the underlying approval remains valid, resolve fresh attempt/lease issuance without needlessly asking for full reapproval; do not mint any lease until separately authorized. If the approval grant itself expired, materialize a typed actionable Human approval request or delegated-authority request via a qualified route and persist evidence of its presentation/dispatch. A request is NOT an approval. If no route is qualified, fail explicitly `AUTHORITY_REQUEST_UNROUTED` and preserve allowed Controller-only recovery instead of silent WAIT_CONTROLLER.
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
