---
name: superpowers-chatgpt
description: Use when designing, planning, implementing, debugging, reviewing, testing, verifying, or completing software work in ChatGPT or an Agent Skills-compatible host.
license: MIT
compatibility: ChatGPT Skills, Workspace Agents, Codex, and Agent Skills-compatible runtimes. External tools remain permission-scoped.
metadata:
  upstream-repository: obra/superpowers
  upstream-commit: 44c9b2d6e889982ac18c27d05a19fefe335194e1
  upstream-release: v6.2.0
  port-version: "0.2.0"
---

# Superpowers for ChatGPT

ChatGPT compatibility adaptation of the MIT-licensed `obra/superpowers` methodology.

## Priority

1. Direct user instruction and explicit authorization.
2. Repository `AGENTS.md`, project-local rules, and governance contracts.
3. The matching workflow below.
4. General engineering judgment where the above are silent.

Never use this skill to bypass approvals, protected branches, security controls, or production safeguards.

## Skill-first rule

Before any software response or action—including clarification or repository inspection—classify the task and apply the relevant workflow. Process workflows take priority over implementation techniques.

| Trigger | Workflow |
|---|---|
| New feature, component, architecture, integration, or behavior change | Brainstorming and design |
| Approved design needs tasks | Writing plans |
| Approved plan needs implementation | Executing plans + TDD |
| Approved plan has mostly independent tasks and real subagents | Subagent-driven development |
| Bug, failing test, incident, unexpected output, regression | Systematic debugging |
| Patch, code, task diff, or PR review | Code review |
| Claim of fixed, complete, ready, safe, deployed, or merged | Verification before completion |
| Completed branch needs integration decision | Finishing a branch |

## Capability and honesty gate

Use only tools actually available. Do not invent a terminal, repository write, subagent, test result, commit, PR, CI result, deployment, or external action. When a required capability is missing, produce the strongest useful fallback and label it unexecuted or unverified.

Read before writing. Work on an isolated branch/workspace. Do not write directly to protected `main`. Merge, deploy, destructive deletion, publication, secrets, migration, production configuration, and production-data writes require explicit authority unless the current request clearly grants it.

## Brainstorming and design

Use before creating new behavior unless the user explicitly authorizes a bounded direct implementation.

1. Inspect project instructions, architecture, tests, and existing patterns.
2. Resolve purpose, users, constraints, interfaces, success criteria, and non-goals.
3. Present two or three viable approaches; lead with the recommendation and compare complexity, risk, maintainability, migration cost, and reversibility.
4. Define architecture, components, interfaces, data flow, errors, observability, security, rollout, rollback, and testing as relevant.
5. Obtain design approval before implementation planning.
6. Save the design in the project-required location and self-review it for ambiguity and contradiction.

## Writing plans

After design approval, produce tasks precise enough for another engineer to execute without reconstructing intent. Each task specifies purpose, exact files to read/write, test first, smallest implementation step, verification command/result, dependencies, and material risks. Separate independent tasks and add checkpoints before risky writes, migrations, external actions, deploys, or merges.

## Executing plans

1. Verify repository, default branch, exact base SHA, working state, instructions, and baseline tests.
2. Create or verify an isolated branch/workspace.
3. Preflight the plan for contradictions, missing dependencies, and instructions that would violate review policy.
4. Maintain a durable task ledger and execute in dependency order.
5. For each task: RED → GREEN → REFACTOR, focused validation, one review with separate spec-compliance and code-quality verdicts, scoped fixes, and scoped re-review.
6. Run one broad whole-change review after all tasks.
7. Verify the final state before any completion claim.
8. Continue until PASS, BLOCKED, FAILED, or exact human authority is required; do not stop merely to ask whether to continue.

## Subagent-driven development

Use only when real dispatch/resume tools exist. Never run multiple implementation agents concurrently against the same working tree.

Each plan owns:

```text
<repo-root>/.superpowers/sdd/<plan-basename>/
```

The ledger begins:

```text
# SDD ledger — plan: <plan-file-path>
```

Do not treat another plan's directory or legacy `.superpowers/sdd/progress.md` as current state. After compaction, trust the plan ledger and `git log` over recollection.

Per task:

1. Record base commit and create a task brief file.
2. Dispatch one fresh implementer; requirements live in the brief, not pasted session history.
3. Implementer tests, commits, self-reviews, and writes a report.
4. Dispatch one task reviewer returning two verdicts: spec compliance and code quality.
5. Fix rounds 1–3 resume the same implementer when supported; rounds 4–5 use a fresh, more capable implementer.
6. Scoped re-review follows every fix round.
7. At round 5, adjudicate all residual findings. Any load-bearing finding makes the task BLOCKED.
8. Record completion and commit in the plan ledger.

After all tasks, run one broad whole-branch review, one bounded final fix and scoped re-review, then delete only this plan's SDD workspace after the review is clean.

Without subagents, use sequential implementer → combined reviewer → fix → scoped re-review → whole-change review passes. Do not fabricate agent identities or resumes.

## Test-driven development

1. **RED:** write the smallest meaningful test and run it; confirm expected failure.
2. **GREEN:** implement the smallest change and run the focused test.
3. **REFACTOR:** improve structure without changing behavior; rerun focused and relevant regression tests.
4. **CHECKPOINT:** record scoped change and fresh evidence.

A good test protects observable behavior and is falsifiable. Name the production change that would make it fail and derive expected values independently. Avoid string-presence/grep tests as proof of behavior, assertions that mirror implementation, constant assertions, and mocks that only prove the mock was called. For config, infrastructure, prompts, or docs, use the closest executable validation. A bug regression must fail on the broken baseline and pass after the fix.

## Systematic debugging

Do not start with speculative fixes.

1. Reproduce and bound the symptom; record exact environment, inputs, timing, logs, versions, and recent changes.
2. Trace data/control flow and find the first divergence from expected behavior. Check contracts, serialization, auth, concurrency, caching, config, network, and storage boundaries.
3. Form a small number of evidence-backed hypotheses, rank them, and test one variable at a time.
4. Add a regression test, implement the smallest root-cause fix, verify original symptom and regressions, and remove temporary diagnostics unless they are useful observability.

Measure before optimizing performance.

## Code review

Review exact requirements, project rules, and diff. Return two separate verdicts:

- **Spec compliance:** approved behavior, missing requirements, unapproved scope, public-contract changes, project/governance compliance, required tests/artifacts.
- **Code quality:** correctness, security, data integrity, migrations, concurrency, failure handling, maintainability, test falsifiability, observability, performance, compatibility, rollout, rollback.

Order findings by severity: Critical, High, Medium, Low. Cite exact files/lines when available. Re-review the actual fix diff; do not assume findings were addressed. A clean quality verdict cannot override a failed spec verdict.

## Verification before completion

Claims require fresh evidence from the current final state.

1. Re-read acceptance criteria and approved scope.
2. Inspect final diff/artifacts.
3. Run focused and broader regression validation.
4. Run build, type, lint, schema, migration, security, or integration checks as applicable.
5. Confirm repository/CI state and no unresolved Critical/High findings.
6. State skipped checks and why.

Report:

- Changed
- Evidence
- Not verified
- Remaining risk
- Repository state

CI green is evidence, not merge/deploy authority.

## Finishing a development branch

First run the full relevant suite on the exact final tree and confirm base branch, approvals, and review state.

For a normal repository or named-branch worktree, present only:

1. Merge locally into the confirmed base
2. Push and create a pull request
3. Keep the branch as-is

For detached HEAD, present only push-as-new-branch/PR or keep-as-is. Execute only the selected or already-authorized option. Preserve the worktree for PR feedback.

Discard is never a normal menu option. It exists only after an explicit request to throw the work away. Show the branch, commits, and worktree that will be deleted, then require the exact confirmation word `discard`. Clean only Superpowers-owned worktrees under `.worktrees/` or `worktrees/`; preserve externally managed or unrelated worktrees.

## DW-SuperApps boundary

This skill is owned by the DW-SuperApps host-control workspace at `.agents/skills/superpowers-chatgpt/`. Registered systems receive no copied skill payload. Installation grants no GitHub, Jira, Slack, merge, deployment, approval, or production authority.

## Attribution

Derived from `obra/superpowers` release v6.2.0, commit `44c9b2d6e889982ac18c27d05a19fefe335194e1`, under the MIT License. This is not an official upstream distribution. Optional upstream visual companion telemetry is not included.