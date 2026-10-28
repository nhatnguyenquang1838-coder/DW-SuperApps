---
name: dw-git-worktree
description: Lightweight task-to-worktree convention for local engineering in registered DW-SuperApps child repositories. Reuse existing worktrees and publish the binding in the task.
---

# DW Git Worktree Convention

This is an engineering convention, not a governance runtime, new gate, scheduler or controller.

## Read canonical sources
- Root `AGENTS.md` — routing and applicable authority
- `workspace.yaml` — registered project and development paths
- `docs/runbooks/ISOLATED_SUBMODULE_WORKTREE.md` — Git worktree lifecycle and safety
- Target project's `AGENTS.md`, if present

## Semantic
**One repository execution unit → one task branch → one reusable worktree**, regardless of which agent or session works on it. `projects/<project>` is a pinned Git submodule/admin anchor; all child source edits occur at `worktrees/<project>/<execution-unit>`.

1. **Resolve:** Identify task, child repository and execution unit from existing task/work-package context. Read the task's latest worktree binding.
2. **Reuse first:** If the binding points to a matching real checkout on this host, continue there. If none exists, a trusted local executor creates/adopts one child-repository linked worktree under the canonical root using the runbook. If stale or conflicting, reconcile rather than silently replace; preserve WIP.
3. **Publish once, update on change:** Add or update the owning Jira/GitHub task with repository, execution unit, branch, worktree relative path, observed HEAD and host when needed. Prefer an established task field/section, otherwise a concise comment. Avoid duplicate comments on no-change ticks.
4. **Engineer normally:** Code → test → fix → commit → push → PR within the bound worktree, subject to existing repo policy.
5. **Optional before commit:** Call Node Architect `git-compliant` **only if the selected workflow requests it**. It reports Git-convention findings; it is not an additional approval gate.
6. **Handoff:** When a worktree binding materially changes or a commit/PR is ready, update the same task so a later agent can recover it.

### Compact task update example
```yaml
worktree_binding:
  repository: <owner/repo>
  execution_unit: <TASK-ID[/WORK-PACKAGE]>
  branch: <task-branch>
  worktree: worktrees/<project>/<execution-unit>
  head_sha: <observed-head>
  host: <host-if-needed>
  status: ACTIVE
```

## Boundaries
- The source runbook remains authoritative for exact Git commands, worktree ownership, WIP preservation, separate parent gitlink integration and protected branches.
- Do not introduce leases, mandatory extra validators, approval steps or orchestration services via this skill.
- Connector-only agents may update remote task metadata but must not claim local `git worktree` operations.
- Do not reset, clean, force-push, delete worktrees or discard scratch/WIP as a side effect of binding.
