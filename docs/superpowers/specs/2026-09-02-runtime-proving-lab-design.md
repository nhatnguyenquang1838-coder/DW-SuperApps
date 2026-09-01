# RuntimePlan Live Certification Suite — W7/W8/W9 Proving Lab Design

Date: 2026-09-02
Status: Draft implementation design bound to TaskController `seq:19`
Run: `RP-HERMES-E2E-W1-W7-20260901-R1`
Campaign: `RP-CERT-001`
Foundation: `nhatnguyenquang1838-coder/DW-SuperApps@769cfd9d840f4521d59d391f567d1c2f2956e545`
Paired GWC: `nhatnguyenquang1838-coder/gwc@43f6379158978b0c299d775cd162ad69b5a1c099`

## 1. Authority and scope

This document materializes the superseding revision in Notion page `3ce07c1c-65b6-817e-81a1-e55eb2a631bb` §12 and the current Jira contracts `SCRUM-676`, `SCRUM-677`, and `SCRUM-678`. It is a repository-local design for a non-production proving campaign. It does not grant merge, deploy, release, production, data, secret, migration, or GWC mutation authority.

The active machine command is the GitHub Controller/Executor mailbox. Slack is pointer-only Human Control Plane transport. The Executor must continue the same run/worktree/branch, must not reset/rebase/force-push, and must report only through its single mutable mailbox comment.

TaskController seq19 is a bounded master execution plan. The Executor performs the ordered tasks in this document and the corresponding plan; it does not invent a replacement plan. Any effect requiring missing or expired exact authority stops with `AUTHORITY_REQUIRED`. Any unavailable required external certification capability stops with `CERTIFICATION_BLOCKED` and preserves evidence.

## 2. Canonical principles

1. **Campaign mutable; TestRuns immutable.** A campaign accumulates runs, findings, corrections, and stability state. A terminal TestRun is never rewritten.
2. **A failed TestRun remains FAIL forever.** A fix is demonstrated only by a successor TestRun bound to new exact evidence.
3. **Exact source identity is forensic identity.** Every run binds runtime repository/branch/start/end SHA, proving-subject repository/branch/start/end SHA, exact GWC SHA, RuntimePlan ref/revision/digest, cursor/evidence, executor/model, authority, and CI refs.
4. **RuntimePlan constrains execution but never grants authority.** Effectful steps revalidate current exact authority at entry.
5. **Declared topology controls outcomes.** Typed outcomes may select only declared edges; provider/controller suggestions cannot create routes, actions, gates, or authority.
6. **Retries are not replans.** A transient retry keeps plan revision/digest. Material source, route, base, or scope drift creates an immutable successor plan and an explicit cursor switch.
7. **Branches are durable evidence.** The campaign may reuse its proving branch for new exact runs; reset, force-push, destructive clean, history rewrite, and deletion of PASS/FAIL evidence are forbidden.
8. **Slack/Notion are projections.** They may display canonical state but never supply machine truth or recovery context.
9. **CI is exact-head evidence.** A check is accepted only when its run/check identity is bound to the exact SHA under test and has reached a terminal conclusion.
10. **W8/W9 are proving, not production delivery.** All runtime-lab and proving branches remain Draft/non-production and are never merged or deployed by this campaign.

## 3. Domain model

### 3.1 TestCase

`TestCase@revision` is the stable scenario contract. For `TC-RP-001`, the declared workload is the real DW Observatory Login UX slice: `/login`, labelled email/password controls, deterministic local validation, deterministic local loading/feedback, accessibility, responsive usability, and test/typecheck/build evidence. Supabase Auth, OAuth, session/cookie middleware, redirects, protected routes, logout, secrets, production data, deploy, and G6 are explicitly out of scope.

### 3.2 CertificationCampaign

`CertificationCampaign` is the long-lived mutable aggregate. It owns `campaign_id`, mode, runtime branch, proving branch, TestCase ID/revision, baseline runtime/subject SHAs, paired GWC SHA, branch ownership, event-store state, findings/corrections, and campaign status. Ownership is keyed by `(repository, branch) -> campaign_id`; the obsolete `branch -> run_id` rule is removed.

### 3.3 TestRun

`TestRun` is a terminal immutable evidence record. Its nested evidence is deeply frozen, and serialization returns detached plain data. It records exact source identities, plan/cursor snapshots, mailbox sequences, executor/provider/model identity, authority receipts, CI checks, expected/actual result, verdict, and evidence-manifest digest. Mutating caller-provided or serialized nested mappings must not change the stored record or digest.

### 3.4 RuntimeFinding and RuntimeCorrection

`RuntimeFinding` identifies a reproducible invariant violation discovered by a specific run, including severity, expected/actual values, invariant ID, reproduction references, and status. `RuntimeCorrection` binds one or more findings to a RED regression, an exact runtime SHA, and successor-run evidence. A finding cannot become resolved without all three kinds of proof.

## 4. Source and workspace identity

The foundation workspace is the existing isolated DW worktree:

```text
/Users/mac/prj/DW-SuperApps.worktrees/scrum-669-r2-dw
branch: auto/SCRUM-669-R2-DW-20260901
head: 769cfd9d840f4521d59d391f567d1c2f2956e545
PR: DW-SuperApps#116 (Draft/Open)
```

The paired GWC checkout is read-only for this campaign:

```text
/Users/mac/prj/gwc.worktrees/scrum-669-r2-m1m4
branch: auto/SCRUM-669-R2-M1-M4
remote: git@github.com:nhatnguyenquang1838-coder/gwc.git
head: 43f6379158978b0c299d775cd162ad69b5a1c099
PR: gwc#550 (Draft/Open)
```

When the real application subject is introduced, runtime and subject must be distinct isolated worktrees/checkouts even though both are in DW-SuperApps. `projects/dw-observation` remains an administration anchor; child source edits occur only in `worktrees/dw-observation/<execution-unit>`. The campaign never collapses runtime and subject into one identity and never implicitly bumps the parent gitlink.

## 5. Branch and PR strategy

The foundation branch remains the W7 implementation branch until revised W7 is terminal and exact-head green. The campaign then creates, without history rewriting:

```text
runtime-lab/RP-CERT-001
prove/RP-CERT-001/TC-RP-001
```

Both branches have Draft PRs and remain non-production. The runtime-lab branch contains runtime corrections. The proving branch contains only the bounded Login UX workload and may be reused inside this campaign. Replays use a normal baseline-restore commit limited to declared TestCase paths; historical commits and all prior TestRun records remain retained.

## 6. Durable evidence and recovery

The event store is append-only and tamper-detecting. Events carry schema version, monotonic event sequence, aggregate ID, payload, previous digest, and record digest. Recovery replays the store and legacy W7 JSONL records deterministically. Invalid digest chains, conflicting sequences, unsupported schemas, or incompatible legacy records fail closed with explicit evidence.

A fresh Controller or Executor recovers only from canonical repository/run identity, Controller and Executor mailbox cursors, RuntimePlan reference/revision/digest, Run Cursor, event store, exact PR/SHA/CI/artifact references, and the persisted Human Plane RootCard binding. No GPT transcript or Slack thread replay is allowed.

## 7. Stability contracts

### W8

`W8_STABLE` requires three consecutive qualifying clean TestRuns for the same semantic runtime SHA, exact GWC SHA, TestCase revision, and bounded plan semantics. Each must have terminal exact-head CI green, complete immutable evidence, no plan/runtime bypass, no unauthorized effect, no stale/duplicate Executor sequence accepted, no unresolved P0/P1 finding, and at least one fresh-Controller recovery proof. Any P0/P1 semantic runtime correction resets the streak to zero.

### W9

W9 starts only from recorded W8 stability. The mandatory cases are:

- C1: three exact-SHA CI fail → declared bounded repair → PASS cycles.
- C2: three hard Controller/session restart recoveries without conversation or Slack replay.
- C3: three legal Executor/provider/model handoffs covering at least two identities, with stale predecessor rejection.
- C4: three materially distinct drift classes producing fail-closed zero-effect behavior and immutable RuntimePlan r2.
- C5: the full declared route/action/authority injection matrix with 100% zero-effect and zero-state-advance rejection.
- C6: three independent Human Plane reconstructions from canonical state only.
- C7: conditional real Node Architect Research convergence, or explicit `NOT_APPLICABLE_CONDITION_UNMET` when canonical convergence is unavailable.

A W9 P0/P1 runtime correction invalidates W8 and requires three new qualifying W8 runs on the final semantic runtime SHA before final certification.

## 8. Authority and zero-effect boundary

RuntimePlan is not authority. Before any effectful operation, the runtime validates the current exact G2 scope, repository, branch, SHA, allowed paths/actions, expiry, and paired source bindings. Missing, stale, mismatched, injected, or out-of-scope authority yields a deterministic fail-closed result. The proof must show zero callbacks, zero repository effects, unchanged cursor/completed steps/evidence/accepted sequence, and no unauthorized mailbox advancement.

The campaign may automate evidence collection, branch preparation, plan compilation, test execution, CI observation, and verdict calculation. It may not manufacture G2/G4 authority, approve production actions, merge, deploy, or replace an in-session exact-head CI wait with a detached scheduler.

## 9. Completion definition

The design is complete only when Tasks 0–16 of the companion plan are complete, revised W7 is terminal, W8 is stable on the final runtime/GWC/TestCase source set, all mandatory W9 thresholds are met or C7 is explicitly conditional-unmet, any P0/P1 corrections have been followed by W8 requalification, zero P0/P1 finding remains unresolved, a fresh verifier reconstructs the campaign from durable evidence, and Jira/GitHub/Notion/campaign-store projections are reconciled. All PRs remain Draft/unmerged/undeployed.

## 10. Seq19 preflight evidence

- Controller mailbox exact-read: `issues/103#issuecomment-5489281895`, `seq:19`, command `cmd-019-w7-w9-runtime-proving-lab-master-execution`.
- Executor mailbox exact-read: `issues/103#issuecomment-5489283690`, `seq:14`, `version:19`, consumed Controller seq `18`.
- Notion page fetched: `3ce07c1c-65b6-817e-81a1-e55eb2a631bb`, §12 superseding revision present, verification state `unverified`.
- Jira descriptions fetched: `SCRUM-676` W7, `SCRUM-677` W8, `SCRUM-678` W9; all current descriptions carry the 2026-09-02 superseding contracts.
- Seq19 MoA: exactly one invocation attempted with `auxiliary.moa_reference.timeout=1200s`; `/tmp/moa_seq19_timeout_measure.txt` contains only `Warning: Unknown toolsets: hud`, so no synthesized receipt fields were returned. Per contract, no retry is permitted; execution continues with the current Hermes model and this limitation remains explicit.
