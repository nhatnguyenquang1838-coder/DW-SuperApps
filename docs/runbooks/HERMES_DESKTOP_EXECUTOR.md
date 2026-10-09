# Hermes Desktop — TaskController Executor Runbook

**Scope:** DW-SuperApps TaskController missions executed in Hermes Desktop.
**Authority:** This is a host runbook, not a new runtime, transport, permission, or gate.

## Canonical boot order

1. Read [root AGENTS.md](../../AGENTS.md), `workspace.yaml`, and [TaskController registry](../../controllers/taskcontroller.yaml).
2. Read [agent index](../../agents/README.md), [A2A contract](../../agents/shared/taskcontroller-a2a-protocol.md), and [Hermes instructions](../../agents/hermes/agent-instructions.md).
3. Recover exact Controller event/cursor, Executor cursor, durable continuation, run/attempt identity, source refs, scope, and authority.
4. Before local mutation of a registered submodule, read [Executor worktree policy](../../controllers/executor-worktree-policy.md) and [isolated worktree runbook](ISOLATED_SUBMODULE_WORKTREE.md).
5. Apply GWC or other project governance only when active for the specific task.

Repository contracts and exact evidence prevail over this runbook or a Desktop prompt. A `hermes-cloud` provider binding does **not** prove an event adapter exists in Hermes Desktop.

## Modes

| Mode | Trigger | Behavior |
| --- | --- | --- |
| Manual-assisted | Human opens the bound Desktop session with an exact Controller event ref | Read and validate the event first; a human prompt does not itself confer authority. |
| Unattended | Verified provider mailbox-event notification | Fetch only the referenced newer event; require a demonstrated Desktop delivery/consumption path. |
| Paused / idle | User pause, no valid event, or hard boundary | No effects, scheduled mailbox polling, automatic `/goal` start, or Slack machine wakeup. |

Use native **`/goal`** for one bounded authorized execution mission. `/goal <text>` starts its first turn immediately, so do **not** set or resume a goal until prechecks pass. Never use `/loop` or heartbeat as a mailbox polling substitute. The `/goal` judge, turn count, and stop reason are **not** canonical TaskController results.

## Six-step execution procedure

### 1 — BOOT (exact recovery)
- Recover canonical mailbox/v2 event/cursor and immutable continuation; do not scan GitHub issue history or rely on Slack for machine state.
- Bind run/node, Controller epoch/seq, Executor last-seen seq, actor/session, branch/head, plan, scope, and provider identity.
- Reject stale/duplicate/conflicting events, sequence gaps, digests or schema mismatches; never silently downgrade to mutable mailbox/v1.

### 2 — PRECHECK (fail closed)
- Validate contract mode (`EXECUTE` for real implementation), approval, current lease time, fencing/generation, idempotency, scope, source/base/head, worktree and stop boundaries.
- Verify the user has not paused/cancelled. Require the durable continuation persisted before dispatch.
- Missing capability or invalid binding means **no `/goal` and no repository effects**. Report a canonical Controller-owned blocker when permissible.

### 3 — EXECUTE (native Hermes goal)
After all checks pass, set **one** goal in the bound Desktop session using exact variables from the validated contract:

```text
/goal Complete <work-packages> for <run_id> on <approved branch>.
verify: <acceptance criteria; tests; exact-head and mailbox evidence>
constraints: Only <approved actions and paths>; preserve <immutable artifacts>; obey lease/fence; no unauthorized PR/merge/deploy/production/secrets.
boundaries: <approved writable roots and execution identity>
stop when: paused, expired authority, material drift, missing capability or hard blocker.
```

The goal text is an execution aid, **not** authorization or dispatch. Do not use `/goal draft` to invent scope. Optionally add a safe deterministic `/goal gate add <test command>` when permitted; a quality gate cannot override canonical validation.
- Continue implementation → test → in-scope repair → regression under the same **valid** EXECUTE boundary, without repetitive Controller turns.
- Re-check time-bound authority before protected effects and at material checkpoints. `/goal resume` also requires a fresh PRECHECK.
- Do not let a goal's continuation budget drive an expired attempt.

### 4 — VERIFY (actual evidence)
- Verify exact branch/head, approved diff, commands/results, tests and required acceptance criteria.
- Treat `/goal` judge `done`, turn-budget stop, `last_stop_reason`, or desktop session exit as UI state only.

### 5 — REPORT (typed mailbox/v2)
- Emit contracted typed progress, completion or one of the canonical blockers using the runtime-owned MailboxRepository/materializer, not handwritten GitHub JSON or a Markdown E-report.
- Exact-readback the Executor event/cursor and evidence; Controller resumes **on the new Executor event**, never by periodic polling.
- Controller owns `CONTINUE | WAIT_CONTROLLER | TERMINAL` and Human approval. Slack remains a human-plane projection.

### 6 — STOP (bounded)
- Stop on verified completion or a real authority, scope, material-plan or external-dependency boundary.
- Preserve continuation; return to paused/idle. Never self-mint authority, restart the prior event, resume a user pause, or schedule `/loop`.

## SCRUM-781 historical guard (not an executable command)

E9 Controller event `#6058394365`, cursor `#6058397162`, continuation record 23 (`WAIT_EXECUTOR / AWAIT_EXECUTOR_EVENT`), and E5 Executor seq 1 **do not prove Desktop delivery**. The G2 lease expired **2026-10-08T14:24:04Z**; the reported Loop was user-paused at tick 645. **Do not replay the event or resume a goal**. Require canonical Controller authority recovery, new valid successor event/cursor/continuation, qualified Desktop delivery and an explicit release of the pause.

## Acceptance checks

- [ ] Root and Hermes host routing both point to this runbook.
- [ ] Exact event, cursor, continuation, source, lease/fence, scope, actor and user-pause prechecks precede `/goal`.
- [ ] No polling/Slack machine fallback; no assumed `hermes-cloud`→Desktop wakeup.
- [ ] In-scope test/fix work remains one bounded mission; duplicates never execute twice.
- [ ] Exact-head evidence, not `/goal` judge, determines completion.
- [ ] Typed Executor result/readback is available and Controller resumes from event.
- [ ] Desktop unattended mode remains *unqualified* until live delivery + consumption succeeds.

## Upstream host references

[Hermes persistent goals](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/goals.md) · [Hermes Desktop](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/desktop.md). Check command support against the **installed** Hermes version before using it.
