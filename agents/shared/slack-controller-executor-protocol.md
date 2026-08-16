# Slack Controller–Executor Protocol — Legacy Compatibility Note

Status: **superseded for active TaskController Agent interaction**.

The former MVP used one Slack thread as both human visibility and Controller↔Executor progress transport. That architecture is retained only as historical compatibility context.

Current authority is:

- `agents/shared/taskcontroller-a2a-protocol.md` for Agent interaction semantics;
- GitHub reference mailbox as the first pilot Agent binding;
- `agents/chatgpt-agent/slack-controller-mvp.md` for the Slack Human Control Plane.

Do not activate this file as the current machine protocol. Do not treat Slack thread history as canonical TaskController run state, audit storage, or required recovery context.

A legacy Slack-mediated run may use this file only when an explicit compatibility task opts into that old transport and current repository policy permits it.
