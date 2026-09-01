# Runtime Proving Lab W7→W9 Implementation Plan

> **For agentic workers:** execute this plan task-by-task with `superpowers:executing-plans`; keep one task in progress, verify each gate, and stop on a real authority or external capability blocker.

**Run:** `RP-HERMES-E2E-W1-W7-20260901-R1`
**Campaign:** `RP-CERT-001`
**Foundation branch:** `auto/SCRUM-669-R2-DW-20260901`
**Foundation head:** `769cfd9d840f4521d59d391f567d1c2f2956e545`
**Paired GWC:** `43f6379158978b0c299d775cd162ad69b5a1c099`
**Design:** `docs/superpowers/specs/2026-09-02-runtime-proving-lab-design.md`

## Global constraints

- Continue the SCRUM-668 RuntimePlan W1→W7 lane; do not switch lanes.
- W8/W9 are draft proving work, not production delivery.
- No merge, deploy, release, production/config/data/secret/migration/destructive action.
- No GWC mutation without a current exact G2 scope; otherwise report `AUTHORITY_REQUIRED`.
- No reset, rebase, force-push, destructive clean, branch deletion, or history rewrite.
- Slack is pointer-only; GitHub mailboxes and durable evidence are machine truth.
- RuntimePlan constrains execution but never grants authority.
- Code changes follow RED → GREEN → REFACTOR; a regression test must fail before its production fix.
- Use exact isolated runtime/subject workspaces; never edit a registered child source in `projects/**`.
- Every exact-head CI wait remains in-session and is polled to terminal.
- Seq19 MoA was invoked exactly once and produced only the known `hud` warning; do not retry it.

## Task 0 — Durable design/plan materialization

**Files:**
- Create `docs/superpowers/specs/2026-09-02-runtime-proving-lab-design.md`.
- Create this plan.
- Modify root `AGENTS.md` only to link the design and plan under the existing TaskController routing documentation.

**Inputs:** exact Controller seq19/Executor seq14 mailboxes, Notion §12, Jira SCRUM-676/677/678, foundation DW/GWC identities.
**Outputs:** design and plan that preserve campaign/TestRun semantics, source identity, branch strategy, replay rules, stability thresholds, authority/zero-effect boundaries, and non-goals.

- [x] Exact-read Controller and Executor mailboxes before action.
- [x] Verify foundation worktree, branch, exact head, clean status, PR #116, paired GWC remote/head/PR.
- [x] Fetch Notion page §12 and current Jira W7/W8/W9 descriptions.
- [x] Run exactly one seq19 MoA; retain the real receipt and do not retry on failure.
- [ ] Write/link/commit these artifacts.
- [ ] Update Executor mailbox checkpoint `T0_COMPLETE`; continue to Task 1.

## Task 1 — Campaign/domain models and deep immutable TestRun evidence

**Files:** create `taskcontroller/runtime/certification_models.py`; create `tests/taskcontroller/test_certification_models.py`; integrate `live_certification_harness.py` only after RED tests.

**Interfaces:** frozen `SourceRevision`, `TestCase`, `CertificationCampaign`, `TestRun`, `RuntimeFinding`, and `RuntimeCorrection` dataclasses. TestRun evidence is recursively frozen and serializes to detached plain data.

- [ ] RED nested evidence mutation cannot alter state/digest.
- [ ] RED invalid/non-40-hex SourceRevision SHA fails closed.
- [ ] RED TestCase missing revision/declared paths fails closed.
- [ ] RED RuntimeFinding cannot resolve without correction evidence.
- [ ] GREEN minimal deep-freeze, validation, and detached serialization implementation.
- [ ] Run focused model tests and existing runtime-plan immutability tests.
- [ ] Commit `feat(runtime-proving): add campaign evidence domain models`.
- [ ] Mailbox checkpoint `T1_COMPLETE`.

## Task 2 — Append-only durable certification event store + v1 compatibility

**Files:** create `taskcontroller/runtime/certification_store.py`; create `tests/taskcontroller/test_certification_store.py`; integrate the live harness only after RED tests.

**Interfaces:** frozen `CertificationEvent` with schema/event sequence/aggregate/payload/previous digest/record digest and `CertificationStore.append`, `replay`, `load_legacy_runs`.

- [ ] RED missing/wrong digest, broken chain, conflicting sequence, and invalid schema fail closed.
- [ ] RED restart replay reconstructs identical canonical state.
- [ ] RED existing v1 W7 JSONL loads deterministically; incompatible records produce explicit fail-closed evidence.
- [ ] GREEN append-only hash chain with fsync/atomic append using repository portability patterns.
- [ ] Run store and existing W7 harness tests.
- [ ] Commit `feat(runtime-proving): add durable certification event store`.
- [ ] Mailbox checkpoint `T2_COMPLETE`.

## Task 3 — Campaign-scoped LiveCertificationHarness

**Files:** modify `taskcontroller/runtime/live_certification_harness.py` and its tests; create campaign integration tests if needed.

**Interfaces:** `create_campaign`, `register_case`, `start_run`, `record_finding`, `record_correction`, `record_verdict`, `get_campaign`, and `get_run`.

- [ ] RED same campaign + same proving branch + new exact SHA is a new run.
- [ ] RED unrelated campaign claiming the branch is rejected.
- [ ] RED duplicate run identity/source tuple is rejected.
- [ ] RED historical PASS/FAIL and nested evidence remain immutable.
- [ ] RED Slack/Notion projection cannot become machine truth.
- [ ] GREEN branch registry `(repository, branch) -> campaign_id`; preserve only non-conflicting compatibility APIs.
- [ ] Run all harness/model/store tests.
- [ ] Commit `refactor(runtime-proving): make branch ownership campaign scoped`.
- [ ] Mailbox checkpoint `T3_COMPLETE`.

## Task 4 — Exact runtime/subject/GWC checkout identity

**Files:** create `taskcontroller/runtime/proving_workspace.py` and `tests/taskcontroller/test_proving_workspace.py`; modify the TaskController workflow only as required for portable fixtures.

**Interfaces:** frozen `ExactCheckout`; `verify_exact_checkout(binding, canonical_remote)`; `verify_distinct_workspace(runtime, subject)`.

- [ ] RED wrong remote/HEAD, missing checkout, and non-EOL content drift fail closed.
- [ ] RED same root for distinct runtime/subject SHAs fails closed.
- [ ] RED GWC producer source-binding mismatch fails closed.
- [ ] GREEN explicit portable roots; no Mac-only absolute path.
- [ ] CI can provision `.ci/runtime`, `.ci/subject`, `.ci/gwc` at requested exact SHAs without mutating `projects/gwc` gitlink.
- [ ] Run focused workspace tests plus seq17/18 exact-pair regressions.
- [ ] Commit `feat(runtime-proving): bind exact runtime subject and gwc workspaces`.
- [ ] Mailbox checkpoint `T4_COMPLETE`.

## Task 5 — W8/W9 stability engine

**Files:** create `taskcontroller/runtime/certification_stability.py` and `tests/taskcontroller/test_certification_stability.py`.

**Interfaces:** frozen `W8StabilityResult`, `DeepCaseStabilityResult`, `evaluate_w8_stability`, `evaluate_deep_case_stability`, `evaluate_campaign_certified`.

- [ ] RED one/two PASS runs are not stable; exactly three qualifying clean runs are.
- [ ] RED semantic runtime SHA change resets the streak.
- [ ] RED unresolved P0/P1, stale PASS, and W9 P0/P1 correction invalidate stability.
- [ ] RED exact W9 thresholds: C1=3, C2=3, C3=3 with ≥2 identities, C4=3 classes, C5=100%, C6=3, C7 conditional.
- [ ] GREEN evaluator consumes canonical immutable evidence only; no Slack/Notion inputs.
- [ ] Commit `feat(runtime-proving): add deterministic stability evaluation`.
- [ ] Mailbox checkpoint `T5_COMPLETE`.

## Task 6 — Revised W7 integration, exact CI, reconciliation

- [ ] Integration test: one campaign, one reused proving branch, multiple immutable runs, finding/correction, restart from disk, replayed stability.
- [ ] Integration test: isolated runtime/subject roots and paired exact GWC source.
- [ ] Run focused revised-W7 tests and `PYTHONPATH=. pytest tests/taskcontroller/`.
- [ ] Run paired GWC architecture E2E at `43f6379158978b0c299d775cd162ad69b5a1c099`.
- [ ] Fast-forward push the foundation branch; verify exact PR #116 head and all required CI to terminal.
- [ ] Record any new P0/P1 and fix through RED regression/correction; do not equate green CI with semantic completion.
- [ ] Reconcile SCRUM-676/GitHub/designated Notion only when revised W7 AC are all met.
- [ ] Mailbox checkpoint `T6_W7_TERMINAL`; continue immediately unless exact authority/capability is blocked.

## Task 7 — RP-CERT-001 branches, Draft PRs, TestCase revision

- [ ] Create retained `runtime-lab/RP-CERT-001` from exact final revised-W7 foundation head.
- [ ] Create retained `prove/RP-CERT-001/TC-RP-001` from exact protected `main` SHA.
- [ ] Use isolated worktrees; declared subject paths are the Login route/test paths only unless a finding authorizes a runtime-side correction.
- [ ] Record baselines, canonical remotes, worktree roots, paired GWC SHA, and `TC-RP-001` revision `2026-09-02-r1`.
- [ ] Open/retain Draft PRs with clear certification-only/non-production semantics; do not merge.
- [ ] Initialize durable campaign store and branch ownership.
- [ ] Verify no production/config/data/secret/deploy effect.
- [ ] Mailbox checkpoint `T7_CAMPAIGN_READY`.

## Task 8 — W8 Standard Real Run loop until W8_STABLE

Use the real `projects/dw-observation` Login UX workload. Subject validation from the child worktree is `pnpm test`, `pnpm typecheck`, and `pnpm build`. Supabase Auth/session/OAuth/middleware/redirect/protected-route/logout are out of scope.

For every run:

- [ ] Prepare declared subject baseline; if replaying changed files, use a normal bounded baseline-restore commit.
- [ ] Exact-verify runtime, subject, and GWC identities.
- [ ] Compile/persist Blueprint + RuntimePlan and recover/create cursor.
- [ ] Revalidate exact current authority before every effect; absent/expired/out-of-scope authority yields `AUTHORITY_REQUIRED`.
- [ ] Preserve RED → GREEN → REFACTOR evidence through RuntimePlan-bound execution.
- [ ] Run focused tests, `pnpm test`, `pnpm typecheck`, and `pnpm build`.
- [ ] Push proving Draft PR exact head and actively poll exact-head CI to terminal.
- [ ] Record immutable TestRun expected/actual/verdict and all exact identities/evidence.
- [ ] Runtime defect: retain FAIL run; add RuntimeFinding, RED regression, bounded runtime correction on runtime-lab, new runtime SHA, local/full TaskController proof, exact CI, RuntimeCorrection, reset streak, rerun.
- [ ] Clean run: continue until three consecutive qualifying runs on the same semantic runtime SHA.
- [ ] Include one fresh-Controller durable recovery proof without transcript/Slack replay; unavailable real capability is `CERTIFICATION_BLOCKED`, not a simulation PASS.
- [ ] Reconcile SCRUM-677/GitHub/Notion/campaign evidence only at `W8_STABLE`.
- [ ] Mailbox checkpoint `T8_W8_STABLE`.

## Task 9 — W9-C1 exact-SHA CI failure/repair

- [ ] Declare `CI_FAIL -> BOUNDED_REPAIR` before failure.
- [ ] Produce valid failing SHA-A on the Draft proving branch; bind real CI failure to SHA-A.
- [ ] Follow declared repair edge, produce SHA-B, poll exact CI to PASS.
- [ ] Retain immutable FAIL/PASS evidence and repeat three independent cycles.
- [ ] Route runtime defects through finding → RED → correction → successor run and recompute stability.
- [ ] Mailbox checkpoint `T9_C1_STABLE`.

## Task 10 — W9-C2 hard Controller restart

- [ ] Persist legal boundary after completed semantic progress.
- [ ] Terminate/restart the actual controllable Controller runtime without transcript copy or Slack replay.
- [ ] Prove same run/plan identity, same next step, no duplicate effect, no missing evidence, and stale-sequence rejection.
- [ ] If real restart capability is unavailable, preserve `CERTIFICATION_BLOCKED` evidence.
- [ ] Complete three clean recoveries; checkpoint `T10_C2_STABLE`.

## Task 11 — W9-C3 Executor/provider/model handoff

- [ ] Persist a legal boundary and exact handoff command.
- [ ] Alternate identity exact-reads bounded command and current cursor.
- [ ] Prove same plan/no replan solely from identity change, no duplicate effect, stale predecessor rejection, and recorded model identity.
- [ ] Cover three cycles and at least two executor/model identities.
- [ ] Return ownership to Hermes Mac where required; checkpoint `T11_C3_STABLE`.

## Task 12 — W9-C4 material drift and immutable replan

Use at least bound source SHA drift, runbook/route-profile semantic drift, and allowed-scope/base-binding drift.

- [ ] Persist RuntimePlan r1 before each drift.
- [ ] Detect drift before effect and transition to `REPLAN_REQUIRED` with zero effect and unchanged stale-step state.
- [ ] Compile/validate/persist immutable r2, atomically switch cursor, continue under r2.
- [ ] Prove normal retry does not create r2.
- [ ] Record three immutable drift runs; checkpoint `T12_C4_STABLE`.

## Task 13 — W9-C5 illegal route/action/authority injection matrix

Declare and exercise undeclared outcome, non-executable route, undeclared action, later-gate/next-node proposal, and provider `authority_granted=true` claim. Every row must prove deterministic rejection, zero callbacks/repository effects, unchanged cursor/completed steps/evidence/accepted sequence, and immutable row evidence. One unauthorized effect is P0: stop, RED-fix runtime, rerun, invalidate W8. Complete at 100%; checkpoint `T13_C5_STABLE`.

## Task 14 — W9-C6 Human Plane projection integrity

At three campaign boundaries, reconstruct RootCard/progress/current/next/executor/model only from canonical plan/cursor/evidence/mailbox. Compare to Slack rendering without using Slack as input. Missing executor/model identity fails the case. Record three proofs; checkpoint `T14_C6_STABLE`.

## Task 15 — W9-C7 conditional Node Architect Research convergence

Exact-read SCRUM-652 convergence state. If available, execute the real L1→L4 conditional flow with selective stale-lens rerun, exact-current-main validation, and genuine Human-decision detection; research evidence never creates implementation authority. If unavailable, record `NOT_APPLICABLE_CONDITION_UNMET` with source evidence. Checkpoint `T15_C7_DONE`.

## Task 16 — Final requalification and certification

- [ ] Inspect all findings/corrections; zero unresolved P0/P1.
- [ ] Determine final qualifying runtime/GWC/TestCase SHA tuple; stale PASS cannot certify a later runtime SHA.
- [ ] After any W9 P0/P1 correction, rerun W8 to three new qualifying clean runs on the final runtime SHA.
- [ ] Recompute all W9 case thresholds against the final source set and rerun invalidated cases.
- [ ] Run final focused/full TaskController, W8 application validation, paired-GWC architecture E2E, and exact-head CI for every final SHA.
- [ ] Fresh verifier reconstructs verdict/evidence from durable store/mailboxes/GitHub without transcripts/Slack replay.
- [ ] Reconcile Jira SCRUM-676/677/678, GitHub Draft PRs, designated Notion projection, and campaign store.
- [ ] Executor mailbox final state is `CERTIFIED_W8_W9_COMPLETE` with all campaign/run/finding/correction/stability/CI evidence and `merge=false deploy=false`.
- [ ] Only after all conditions are met, issue one final Slack Human Plane report; no intermediate progress reports.

## Completion definition

Tasks 0–16 are complete only when revised W7 is terminal, W8 is `W8_STABLE` on the final source tuple, every mandatory W9 threshold is satisfied or C7 is explicitly conditional-unmet, P0/P1 corrections have triggered W8 requalification, zero P0/P1 finding remains, a fresh verifier reconstructs the evidence, projections reconcile, and all proving/runtime-lab PRs remain Draft/unmerged/undeployed.
