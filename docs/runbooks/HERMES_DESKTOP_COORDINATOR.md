# Hermes Desktop — Coordinator Executor Runbook

**Mode:** COORDINATOR — Hermes Desktop coordinates multiple *bounded child work units* inside **one Controller-approved parent mission**.
**Authority:** Host operating procedure, not a new TaskController, authority grant, provider runtime, or automatic fanout activation.
**Default:** Not selected implicitly; [Standalone Mode](HERMES_DESKTOP_STANDALONE.md) covers atomic/single-Executor missions.

## What Coordinator means (and does not mean)

- GPT TaskController remains the **Controller** and exclusive Human/gate-authority router. Hermes is the **Executor**, with a delegated internal coordination responsibility; it does **not** become an independent TaskController.
- The parent Controller event must explicitly bind a child-capable execution plan: `max_children > 0`, depth/parallel budgets, approved child objectives, scope, source, writer ownership, and allowed effects. A complex task alone is **not** a delegation grant.
- `taskcontroller/execution/child_contract.py`, `fanout.py`, and `manifest.py` describe validated bounded child contracts and fanout planning/state normalization. **They do not spawn workers or enable the provider.** Actual child dispatch requires an available, qualified adapter and canonical authority.
- Native Hermes `delegate_task` can be an execution mechanism **only when present in the installed Desktop build**, compatible with the selected Controller contract and explicitly permitted. It is not a canonical mailbox or approval mechanism.
- For SCRUM-781 E9 T1–T7, `max_children=0`, the lease is expired and the Loop is user-paused. **Coordinator Mode is not authorized for that event.** Do not infer a role change, replay it or resume work.

## Canonical sources and activation

Read [root AGENTS.md](../../AGENTS.md), `workspace.yaml`, [TaskController registry](../../controllers/taskcontroller.yaml), [agent index](../../agents/README.md), [A2A protocol](../../agents/shared/taskcontroller-a2a-protocol.md), and [Hermes instructions](../../agents/hermes/agent-instructions.md). If the target is a registered submodule and any child will mutate code, also read [worktree policy](../../controllers/executor-worktree-policy.md) and [isolated submodule worktree runbook](ISOLATED_SUBMODULE_WORKTREE.md). Resolve project/GWC rules only when activated by the exact task.

Canonical mailbox/v2 records and active source/authority precede this runbook and any Desktop prompt. A `hermes-cloud` event-subscription declaration does **not** prove Hermes Desktop delivery. A human-opened Desktop session may begin read-only preflight but does not grant execution rights.

## Six-step Coordinator process

### 1 — BOOT: recover the exact parent

- Read the **exact** new Controller event/cursor, last accepted Executor cursor, immutable continuation, run/node, attempt/generation, actor/session and source/head. Never reconstruct authority from full issue history, Slack or Loop memory.
- Verify a Controller-owned, current parent contract; confirm the requested mode is COORDINATOR with permitted delegation, provider/worker bindings and stated join policy.
- Verify user pause/cancel state. A paused host must not dispatch children or restart a goal.

### 2 — PRECHECK: validate parent and child envelopes

- Require valid approval, lease, fencing token, source/base/head, execution boundary, writable paths, `max_children`, `max_depth`, `max_parallel`, per-child authority and continuation checkpoint **before any effect**.
- Validate the declared execution mode. `PLAN` may analyze/decompose without repository effects; `EXECUTE` with live authority is required for mutation. Parent authority is **not** an unrestricted grant for children.
- Reconcile Hermes runtime capability: `delegate_task` availability, configured concurrency/depth, callback/session delivery, resource limits, and workspace isolation. Effective limits are the stricter of the **canonical parent contract** and the **working provider configuration**. No guessed values.
- If `max_children=0`, coordinator is prohibited. If the provider is unavailable, do not fake child receipts or silently downgrade a required child topology to sequential execution. Report a material capability blocker through the contracted Controller path.
- If an ordinary standalone implementation is separately authorized, use the [Standalone runbook](HERMES_DESKTOP_STANDALONE.md) for that **separate** mission; do not mutate an existing immutable parent plan.

### 3 — DECOMPOSE and DISPATCH: bounded fanout

Define a minimal DAG and child table before dispatch:

| Child binding | Mandatory evidence |
| --- | --- |
| Stable identity | `child_id`, `parent_run_id`, parent contract digest and child objective |
| Correct boundary | child scope subset proof, explicit allowed actions, exact source and standards references |
| Dependency | predecessors, stage, concurrency and writer ownership |
| Execution identity | actor/provider/session, attempt, lease/fence, maximum depth |
| Completion contract | acceptance criteria, structured result/evidence refs and timeout/blocker rules |

- Use the canonical child-contract/fanout APIs **only** for their supported validation/planning semantics. Materialize or dispatch through a real approved provider binding; retain a durable Fanout Manifest/receipt **only if the configured runtime supports it**.
- Prefer parallel **read-only** research or independent review children. Dispatch mutable children only with separately established execution identities, non-overlapping scopes, and one writer per branch/worktree; never allow two children to write the same working tree.
- DW-SuperApps registered submodules require `worktrees/<project>/<execution-unit>` under the workspace root. Hermes's generic optional auto-isolation under `.worktrees/subagent-*` is **not** a substitute for this workspace policy. Provision/check compliant worktrees through authorized tooling before assigning write work.
- Inherit child capabilities only as permitted by the provider; inherited tools are **not** inherited effect authority. Do not send raw secrets, unbounded chat history, or unaudited claims as contracts.
- If the installed Hermes version supports `delegate_task`, use its structured single/batch interface with exact bounded goals and context. Nested `role="orchestrator"` is only permitted when **both** the parent contract permits deeper delegation and installed provider config actually enables that depth. Default to no nested delegation.
- Start a single bounded native Hermes `/goal` for coordination only **after** BOOT/PRECHECK; it is a local work aid, not a dispatcher, approval, authority or result record. Do not use `/loop` to wait for children/mailbox events.

### 4 — COLLECT, REVIEW and JOIN: one accountable parent

- Consume child completion callbacks/receipts through the qualified provider and check exact identity, stale/cancelled generations, source/digests and evidence. Never treat a child summary or the parent's goal judge as proof of success.
- Cross-review may use independent read-only children **within** the contracted budget. Reviewers must not share a mutable workspace with the author.
- Join deterministic results by **stable child ID**, not arrival order. The current `FanoutCoordinator` supports `ALL_REQUIRED`: only successfully verified required children produce a READY join; failed/timed-out/cancelled/stale children block it. Do not invent quorum or partial-success acceptance.
- For each required child: record completion state, acceptance evidence, exact artifacts/commit refs, test findings and provenance. Deduplicate retried or out-of-order notifications before accepting a result.
- If integration is approved, perform it using a **single designated integration writer**, with exact branch/base/diff controls. Child completion alone does not authorize integration, PR, merge or deployment.

### 5 — VERIFY and REPORT: parent synthesis

- Parent checks every accepted child result against the parent acceptance criteria; run broader integration/regression and exact-head validation where contracted.
- Emit **one** canonical typed Executor mailbox/v2 semantic report (plus contracted material progress/blockers) with parent/child refs, join disposition, evidence and next boundary using the runtime-owned repository/materializer.
- Exact-readback resulting Executor event/cursor. The GPT Controller resumes **only on a newer Executor mailbox event** and owns `CONTINUE | WAIT_CONTROLLER | TERMINAL`, further grants and Human interactions.
- Do not publish to Slack as machine notification; no periodic polling, manually authored event JSON, fabricated digest or child provenance.

### 6 — STOP / RECOVER: fail closed without churn

Stop new dispatch and protected effects for user pause, expired parent or child lease, identity/source drift, budget violation, capability failure, unavailable required dependency or a material plan change. Map the blocker to the canonical Controller-owned classes in [Hermes instructions](../../agents/hermes/agent-instructions.md).

- Preserve exact durable parent/child records and partial results; do not infer that restarting Desktop resumes children. Native subagent sessions may be cancelled on parent/session shutdown.
- Recover from canonical continuation, current Controller/Executor event/cursor and actual provider receipts; a fresh approval/successor event is needed where authority expired or scope changed.
- Routine in-scope child test/fix remains inside that child's bounded contract; do not cycle back to Controller between every RED/GREEN step.
- Never convert the parent's `/goal` stop reason or number of child completions into an overall SUCCEEDED result without join and exact evidence.

## Completion checklist

- [ ] Mode explicitly selected and bound to a **valid child-capable parent** (`max_children>0`).
- [ ] No unqualified Hermes Desktop event-delivery or subagent capability asserted.
- [ ] Parent/child scope, lease/fence, execution limits and writer ownership checked.
- [ ] Child contracts reference parent identity; no permission escalation, nested-depth drift or parallel write conflict.
- [ ] Child callbacks are identity-checked and idempotently processed; no polling/busy Loop.
- [ ] Verified stable-ID `ALL_REQUIRED` join; partial/failed/stale children are not silently accepted.
- [ ] Parent integration/tests and exact refs are verified, not inferred from agent final text.
- [ ] Canonical typed Executor mailbox event and cursor are exact-read back; Controller retains gate/Human authority.
- [ ] User pause and expired SCRUM-781 E9 event remain untouched.

## Upstream Hermes reference

[Hermes subagent delegation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/delegation.md). Check command/tool/config availability against the **installed Desktop version** before use; upstream defaults are not a substitute for current host/protocol readback.
