# OpenClaw ACPX Orchestrator

This package makes OpenClaw the DW SUPER control plane and exposes Codex, Claude Code, Kiro CLI, and Kilocode as external ACP workers.

## Scope

This first slice provides:

- official `@openclaw/acpx` installation and configuration;
- a strict four-worker allowlist;
- persistent thread-bound ACP sessions;
- DW Power skill loading through the existing generic adapters;
- governed dispatch guidance;
- normalized work-order and worker-result schemas;
- Bash and PowerShell installers.

It does not implement automatic task routing, worktree creation, pull requests, CI remediation, or merge automation yet.

## Install

Linux, macOS, WSL, or Git Bash:

```bash
bash hosts/openclaw-acpx/install.sh
```

Restart immediately when no OpenClaw work is active:

```bash
bash hosts/openclaw-acpx/install.sh --restart
```

Windows PowerShell:

```powershell
.\hosts\openclaw-acpx\install.ps1
```

Or restart immediately:

```powershell
.\hosts\openclaw-acpx\install.ps1 -Restart
```

The installer first generates the generic DW Power adapters under `.agents/skills`, then configures OpenClaw to load those adapters together with `hosts/openclaw-acpx/skills`.

## Verify

```bash
openclaw skills list
openclaw gateway restart
```

In an OpenClaw conversation:

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

`openclaw.config.json` is a reference profile. The installers resolve `<DW_SUPER_ROOT>` to the current repository path and write settings through `openclaw config set`.
