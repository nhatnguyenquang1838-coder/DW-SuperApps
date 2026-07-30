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

## Profile-aware bootstrap

Use an explicit profile when OpenClaw runs an isolated DW SUPER configuration.

Bash, Zsh, Linux, macOS, WSL, or Git Bash:

```bash
bash hosts/openclaw-acpx/install.sh --profile gwc --restart
```

Windows PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1 -Profile gwc -Restart
```

Omit `--profile` or `-Profile` only when the default OpenClaw profile is intentionally the target.

The installer is script-owned and does not require manual editing of `openclaw.json`. It:

1. generates generic DW Power adapters;
2. installs the official `@openclaw/acpx` plugin;
3. applies targeted settings with `openclaw config set`;
4. prints the active config path;
5. validates the selected profile;
6. reads back every governed ACPX value and fails on mismatch;
7. restarts only the selected gateway when requested.

Every OpenClaw command uses the same profile prefix:

```text
openclaw --profile <name> ...
```

This includes plugin installation, config writes, config reads, validation, and gateway restart.

## Read existing config without changing it

Bash:

```bash
bash hosts/openclaw-acpx/install.sh --profile gwc --verify-only
```

PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1 -Profile gwc -VerifyOnly
```

Verification-only mode performs no adapter generation, plugin installation, config write, or gateway restart.

It reads:

- the selected config file path;
- config schema validity;
- ACP enablement and backend;
- dispatch enablement;
- exact worker allowlist;
- persistent session binding;
- fail-closed permissions;
- disabled MCP bridges;
- DW SUPER skill directories and watch mode.

Direct read-only inspection remains available:

```bash
openclaw --profile gwc config file
openclaw --profile gwc config validate
openclaw --profile gwc config get acp.enabled --json
openclaw --profile gwc config get acp.allowedAgents --json
openclaw --profile gwc config get skills.load.extraDirs --json
```

## Capability verification

After the script passes, run in an OpenClaw conversation on the same profile:

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
- one target project;
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
- The installer changes only declared ACPX and skill-loading config paths.
- Unrelated OpenClaw models, providers, auth profiles, channels, and gateway settings are preserved.

## Deferred work

This setup intentionally defers:

- automatic routing policy;
- worktree allocator;
- quota telemetry;
- retry and fallback reconciliation;
- GitHub PR and CI reaction loops;
- GWC gate-event persistence;
- Slack thread projection.

Those belong to the next governed slices after `/acp doctor` and all four worker probes pass.
