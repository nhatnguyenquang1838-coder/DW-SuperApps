---
name: dw-dispatch-worker
description: Dispatch a governed DW SUPER work order to Codex, Claude, Kiro, or Kilocode through OpenClaw ACPX.
metadata: { "openclaw": { "requires": { "config": ["acp.enabled", "plugins.entries.acpx.enabled"] } } }
---

# DW SUPER Worker Dispatch

Use this skill only after the target system, Power set, governance gate, repository base SHA, allowed scope, and validation commands are known.

## Authority

- OpenClaw owns orchestration, worker selection, session control, retries, cancellation, and result reconciliation.
- GWC owns gates, approvals, overrides, bypasses, and audit evidence.
- Task Me owns implementation-task planning.
- UA provides codebase and architecture context.
- GitHub is authoritative for branch, pull request, exact-head CI, and merge state.
- Slack is a communication projection only.

## Worker routing defaults

- `kiro`: requirements, design, specifications, and task decomposition.
- `claude`: architecture analysis, complex debugging, and broad refactors.
- `codex`: bounded implementation, tests, repair, and independent review.
- `kilocode`: provider-flexible execution and quota-aware fallback.

These are defaults. Route based on required capability and current availability.

## Required controls

1. Validate the work order against `{baseDir}/../../schemas/work-order.schema.json`.
2. Use exactly one isolated worktree for one implementing worker.
3. Never allow workers to assign work directly to other workers.
4. Do not silently switch workers after partial edits. Reconcile the worktree first.
5. Do not allow the implementation worker to be the only reviewer.
6. Do not accept a free-form `done` response as completion.
7. Read back Git status, diff, changed paths, commands, test output, branch, and HEAD SHA.
8. Normalize the result with `{baseDir}/../../schemas/worker-result.schema.json`.
9. Keep PR creation, ready-for-review, approval, merge, and post-merge verification under GWC.
10. Fail closed when scope, permissions, base SHA, or approval evidence is missing.

## Permission baseline

The packaged runtime uses:

- `permissionMode: approve-reads`
- `nonInteractivePermissions: fail`
- plugin-tools MCP bridge disabled
- OpenClaw-tools MCP bridge disabled

Do not enable `approve-all` or either MCP bridge without an explicit governed change and audit record.
