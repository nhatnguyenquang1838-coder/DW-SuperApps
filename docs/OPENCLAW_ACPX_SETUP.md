# OpenClaw + ACPX Setup

## Objective

Use OpenClaw as the main DW SUPER orchestrator while Codex, Claude Code, Kiro CLI, and Kilocode perform bounded specialist work through ACPX.

```text
OpenClaw
├── GWC governance and approval control
├── Task Me implementation planning
├── UA codebase and architecture context
└── ACPX workers
    ├── codex
    ├── claude
    ├── kiro
    └── kilocode
```

OpenClaw owns orchestration and session control. Workers do not become task authorities and cannot declare governed completion.

## Bootstrap

```bash
bash hosts/openclaw-acpx/install.sh
openclaw gateway restart
```

PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1
openclaw gateway restart
```

The setup installs the official `@openclaw/acpx` plugin, enables ACP dispatch, registers the four allowed workers, enables persistent thread bindings, and loads DW SUPER skills.

## Capability verification

Run in OpenClaw:

```text
/acp doctor
```

Then smoke-test each configured worker:

```text
/acp spawn codex
/acp spawn claude
/acp spawn kiro
/acp spawn kilocode
```

A failed worker probe is a capability result. It must not silently expand permissions or switch to an unregistered worker.

## Routing defaults

| Worker | Default work |
|---|---|
| Kiro | Requirements, design, specifications, task decomposition |
| Claude | Architecture analysis, complex debugging, broad refactors |
| Codex | Bounded implementation, tests, repair, independent review |
| Kilocode | Provider-flexible execution and quota-aware fallback |

Routing remains capability-based. These defaults do not override GWC scope or approval requirements.

## Execution contract

Before dispatch, OpenClaw must have:

- exact repository and base SHA;
- one target system;
- applicable Powers;
- current GWC gate and risk;
- allowed and forbidden paths;
- isolated worktree and branch;
- validation commands;
- expected normalized outputs.

Use:

- `hosts/openclaw-acpx/schemas/work-order.schema.json`
- `hosts/openclaw-acpx/schemas/worker-result.schema.json`

## Safety

- One task uses one isolated worktree.
- Only one implementing worker is active in that worktree.
- A different worker performs independent review.
- Workers never assign tasks directly to other workers.
- Worker output is evidence, not repository truth.
- OpenClaw reads back Git state and validation output.
- GitHub remains authoritative for branch, PR, exact-head CI, and merge.
- Slack remains a communication projection only.
- Missing scope, permissions, base SHA, or approval evidence fails closed.

## Deferred work

This setup intentionally defers:

- automatic routing policy;
- worktree allocator;
- quota telemetry;
- retry and fallback reconciliation;
- GitHub PR and CI reaction loops;
- GWC gate-event persistence;
- Slack thread projection.

Those belong to the next governed slices after all four worker probes pass.
