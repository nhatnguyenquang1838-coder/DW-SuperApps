# Slack Controller–Executor Protocol — Legacy MVP

Status: **LEGACY / NOT ACTIVE WHEN `dw.taskcontroller.a2a/v1` IS ACTIVE**.

## Compatibility boundary

This document is retained only for explicit legacy compatibility and historical audit. It MUST NOT be loaded as a competing TaskController machine interaction contract when the active controller registry resolves `pilot_binding: github-reference-mailbox`.

For current TaskController sessions, the controlling interaction contract is `agents/shared/taskcontroller-a2a-protocol.md`:

```text
Controller mailbox
→ pointer-only provider wake-up when required
→ Executor mailbox
→ Controller exact-mailbox polling/cursor
→ semantic Human Plane projection
```

Slack is not the machine command/progress/recovery bus for active A2A sessions. A missing mailbox or continuation checkpoint MUST fail closed and MUST NOT cause fallback to this legacy protocol.

## Legacy use only

A host may use this document only when an explicit repository/project contract selects a legacy Slack-only interaction mode and TaskController A2A is not active. Historical terms such as Slack Executor updates, thread polling, and `last_seen_ts` apply only in that explicit legacy mode.

This document grants no governance, approval, merge, deploy, or production authority.
