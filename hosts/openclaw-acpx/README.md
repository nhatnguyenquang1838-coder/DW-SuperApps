# OpenClaw ACPX Orchestrator

This package makes OpenClaw the DW SUPER control plane and exposes Codex, Claude Code, Kiro CLI, and Kilocode as external ACP workers.

## Scope

This first slice provides:

- official `@openclaw/acpx` installation and configuration;
- explicit OpenClaw profile targeting;
- script-owned config validation and read-back;
- a strict four-worker allowlist;
- persistent thread-bound ACP sessions;
- DW Power skill loading through the existing generic adapters;
- governed dispatch guidance;
- normalized work-order and worker-result schemas;
- Bash and PowerShell installers.

It does not implement automatic task routing, worktree creation, pull requests, CI remediation, or merge automation yet.

## Profile-aware install

The installers never edit `openclaw.json` directly. They use `openclaw config set`, validate the selected profile, then read every governed ACPX setting back through `openclaw config get --json`.

Linux, macOS, WSL, or Git Bash:

```bash
bash hosts/openclaw-acpx/install.sh --profile gwc --restart
```

Windows PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1 -Profile gwc -Restart
```

Omit the profile option only when the default OpenClaw profile is intentionally the target:

```bash
bash hosts/openclaw-acpx/install.sh --restart
```

```powershell
.\hosts\openclaw-acpx\install.ps1 -Restart
```

Every OpenClaw command, including plugin installation, configuration, validation, read-back, and gateway restart, is sent to the selected profile.

## What the script performs

1. Generates the generic DW Power adapters under `.agents/skills`.
2. Installs the official `@openclaw/acpx` plugin in the selected profile.
3. Writes only the governed ACPX, session-binding, and skill-loading paths.
4. Prints the active profile config file with `config file`.
5. Runs `config validate`.
6. Reads back and compares all governed values.
7. Restarts the selected profile gateway only when requested.

Unrelated models, providers, authentication profiles, channels, and gateway settings are not replaced.

## Read and verify config without writing

Bash:

```bash
bash hosts/openclaw-acpx/install.sh --profile gwc --verify-only
```

PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1 -Profile gwc -VerifyOnly
```

Verification-only mode does not generate adapters, install plugins, set config, or restart the gateway. It validates and reads the existing selected-profile configuration.

Direct read-only commands:

```bash
openclaw --profile gwc config file
openclaw --profile gwc config validate
openclaw --profile gwc config get acp.allowedAgents --json
openclaw --profile gwc config get plugins.entries.acpx.config.permissionMode --json
```

## Runtime verification

In an OpenClaw conversation on the same profile:

```text
/acp doctor
/acp spawn codex
/acp spawn claude
/acp spawn kiro
/acp spawn kilocode
```

Authentication remains owned by each worker CLI. A successful ACPX installation does not log in Codex, Claude, Kiro, or Kilocode for you.

## Security baseline

The package deliberately configures:

```text
permissionMode              = approve-reads
nonInteractivePermissions   = fail
pluginToolsMcpBridge        = false
openClawToolsMcpBridge      = false
```

This means reads can proceed, while file writes or shell commands fail closed unless the worker and runtime can satisfy the permission contract. Do not switch to `approve-all` globally. Use isolated worktrees and governed per-task scope before enabling implementation writes.

## Files

```text
manifest.yaml
openclaw.config.json
install.sh
install.ps1
skills/dw-dispatch-worker/SKILL.md
schemas/work-order.schema.json
schemas/worker-result.schema.json
```

`openclaw.config.json` is a reference profile. The installers resolve `<DW_SUPER_ROOT>` to the current repository path and apply targeted values through the OpenClaw CLI.
