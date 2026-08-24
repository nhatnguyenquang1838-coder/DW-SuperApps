# TaskController A2A Mailbox Boot P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make reference-based A2A mailboxes the mandatory, fail-closed TaskController machine transport from session start, with Slack limited to the Human Control Plane and pointer-only wake-up.

**Architecture:** Keep the existing `taskcontroller.interaction` mailbox/continuation primitives and make activation/configuration/instructions require them before first Executor dispatch. Remove the active dual-protocol path by treating the old Slack Controller–Executor protocol as legacy-only when A2A is active; Controller and Executor machine state flows through one mutable GitHub mailbox per actor and monotonic sequence/cursors.

**Tech Stack:** Python 3, pytest, YAML/Markdown controller contracts, GitHub reference mailbox, Slack pointer-only wake-up.

**Spec:** `agents/shared/taskcontroller-a2a-protocol.md`

## Global Constraints

- Repository: `nhatnguyenquang1838-coder/DW-SuperApps`.
- Exact design base: `main@fc07d77036929b942dce297a1c4abbeb18e59868`.
- GWC is not active for this change.
- No direct write to protected `main`; use guarded branch + PR + exact-head CI + explicit merge into `main`.
- No force-push, rebase, branch deletion, deploy, production/data/config/secret/migration actions.
- A TaskController session must fail closed rather than fall back to Slack machine transport when mailbox boot/readback is unavailable.
- Slack may carry semantic human projections and a pointer-only wake-up, never the command/progress/recovery payload.

---

### Task 1: Lock mailbox-first activation contract with RED tests

**Files:**
- Modify: `tests/taskcontroller/test_activation_contract.py`
- Modify: `tests/taskcontroller/test_controller_continuation.py`

**Interfaces:**
- Consumes: `resolve_taskcontroller_activation(...)`, `TaskControllerActivationPlan`, `controllers/taskcontroller.yaml`, host overlays.
- Produces: regression assertions that active TaskController requires mailbox boot before first dispatch and forbids Slack machine fallback.

- [ ] **Step 1: Write failing activation tests**

Require active ChatGPT+Hermes TaskController activation to expose mailbox boot as mandatory/fail-closed, machine progress transport as `github-reference-mailbox`, pointer-only Slack wake-up, and Slack machine progress disabled. Require host overlays to contain no active dependency on `slack-controller-executor-protocol.md`.

- [ ] **Step 2: Verify RED**

Run the focused TaskController test workflow/pytest for the exact test-only head. Expected: failure because current activation plan lacks mailbox-boot fields and current ChatGPT/Hermes overlays still route machine progress through Slack.

- [ ] **Step 3: Commit RED evidence**

Commit only test/plan changes before production behavior changes.

### Task 2: Make A2A mailbox boot fail-closed in activation and registry

**Files:**
- Modify: `taskcontroller/mvp/activation.py`
- Modify: `controllers/taskcontroller.yaml`
- Modify: `AGENTS.md`
- Modify: `agents/shared/taskcontroller-a2a-protocol.md`

**Interfaces:**
- Consumes: existing `ControllerContinuation`, `MailboxPollTarget`, GitHub mailbox, WakeupSignal primitives.
- Produces: activation metadata that requires controller+executor mailboxes, continuation/readback before first dispatch, exact-mailbox polling, no Slack machine fallback.

- [ ] **Step 1: Implement minimal activation fields**

Add explicit active-plan properties for mailbox boot required/fail-closed, machine progress transport, Slack machine progress prohibition, and pointer-only wake-up. Inactive plans must not claim an active mailbox requirement.

- [ ] **Step 2: Add registry/session-boot invariants**

Add a mailbox boot section requiring both actor mailboxes, continuation checkpoint, exact readback, and fail-closed behavior before first dispatch. Explicitly forbid Slack fallback as machine transport.

- [ ] **Step 3: Strengthen canonical routing text**

State that TaskController boot is incomplete until mailbox/continuation materialization succeeds; Slack history is never a recovery input.

- [ ] **Step 4: Run focused tests**

Expected: activation/continuation contract tests progress toward GREEN; instruction overlay tests may remain RED until Task 3.

### Task 3: Eliminate dual Slack machine protocol from active host overlays

**Files:**
- Modify: `agents/chatgpt-agent/agent-instructions.md`
- Modify: `agents/chatgpt-agent/slack-controller-mvp.md`
- Modify: `agents/hermes/agent-instructions.md`
- Modify: `agents/shared/slack-controller-executor-protocol.md`

**Interfaces:**
- Consumes: active A2A protocol and mailbox bootstrap metadata.
- Produces: one machine path: Controller mailbox → pointer wake-up → Executor mailbox → Controller; Slack only semantic Human Plane.

- [ ] **Step 1: Rewrite ChatGPT overlay**

Require A2A/mailbox boot at session start before delegation; monitor only exact Executor mailbox/cursor; update Controller mailbox before any new command/correction; no full command/progress payload in Slack.

- [ ] **Step 2: Rewrite Slack Human Plane overlay**

Retain one RootCard and semantic milestone projections, but remove Executor thread-journal semantics and Slack polling as machine progress transport.

- [ ] **Step 3: Rewrite Hermes overlay**

Require Hermes to fetch command from its mailbox after pointer wake-up, execute bounded work, and update its own mutable mailbox in place with monotonic seq. No normal progress narration on Slack.

- [ ] **Step 4: Mark old Slack Controller–Executor protocol legacy-only**

State it is not active when `dw.taskcontroller.a2a/v1` is active and must never be loaded as a competing machine transport.

- [ ] **Step 5: Run focused tests**

Expected: activation + continuation + reference-A2A tests GREEN.

### Task 4: Full validation, PR, and main merge

**Files:**
- Validate all changed files above.

**Interfaces:**
- Produces: exact-head CI evidence and merged main SHA.

- [ ] **Step 1: Run focused TaskController tests**

Require activation, continuation, reference-A2A, wake-up/mailbox tests PASS.

- [ ] **Step 2: Run repository validation/CI**

Bind every check to the exact pushed PR head. If non-terminal, wait in-session and re-read the same SHA until terminal.

- [ ] **Step 3: Review complete PR diff**

Confirm no GWC activation, no production action, no Slack machine fallback, and no unrelated files.

- [ ] **Step 4: Merge to `main`**

Merge only with expected exact head SHA after terminal validation. Read back new `main` SHA and post-merge CI/evidence.

### Task 5: Update canonical Google Drive controller behavior

**Files:**
- Google Doc: `DW SUPER — ChatGPT Agent Materialization & Validation Instruction`

**Interfaces:**
- Consumes: merged repository A2A/mailbox contract.
- Produces: canonical GPT behavior requiring A2A + mailboxes at TaskController session boot.

- [ ] **Step 1: Replace conflicting Slack-machine language**

Replace requirements that use Slack thread replies as the Executor journal/monitoring bus with exact-mailbox polling and semantic Human Plane projection.

- [ ] **Step 2: Add mandatory TaskController mailbox boot doctrine**

Require both actor mailboxes + continuation checkpoint + exact readback before first Executor dispatch; missing boot is `TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED` and must not fall back to Slack machine transport.

- [ ] **Step 3: Preserve no-GWC routing rule**

State TaskController activation does not activate GWC; GWC is loaded only when the current task requires it.

- [ ] **Step 4: Read back the new Drive revision**

Verify the exact updated text and revision ID against the merged repository behavior.