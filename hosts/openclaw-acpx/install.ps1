param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
    throw "openclaw is not available on PATH."
}

$Python = $null
foreach ($Candidate in @("python", "py")) {
    if (Get-Command $Candidate -ErrorAction SilentlyContinue) {
        $Python = $Candidate
        break
    }
}
if (-not $Python) {
    throw "Python 3 is required to generate DW Power adapters."
}

if ($Python -eq "py") {
    & py -3 (Join-Path $Root "scripts\dw_cli.py") host install custom --mode wrapper
} else {
    & python (Join-Path $Root "scripts\dw_cli.py") host install custom --mode wrapper
}

& openclaw plugins install "@openclaw/acpx"
& openclaw config set plugins.entries.acpx.enabled true --strict-json
& openclaw config set acp.enabled true --strict-json
& openclaw config set acp.dispatch.enabled true --strict-json
& openclaw config set acp.backend acpx
& openclaw config set acp.defaultAgent codex
& openclaw config set acp.allowedAgents '["codex","claude","kiro","kilocode"]' --strict-json
& openclaw config set acp.stream.deliveryMode live

& openclaw config set session.threadBindings.enabled true --strict-json
& openclaw config set session.threadBindings.idleHours 24 --strict-json
& openclaw config set session.threadBindings.maxAgeHours 0 --strict-json
& openclaw config set session.threadBindings.spawnSessions true --strict-json

& openclaw config set plugins.entries.acpx.config.permissionMode approve-reads
& openclaw config set plugins.entries.acpx.config.nonInteractivePermissions fail
& openclaw config set plugins.entries.acpx.config.probeAgent codex
& openclaw config set plugins.entries.acpx.config.timeoutSeconds 120 --strict-json
& openclaw config set plugins.entries.acpx.config.pluginToolsMcpBridge false --strict-json
& openclaw config set plugins.entries.acpx.config.openClawToolsMcpBridge false --strict-json

$SkillDirs = @(
    (Join-Path $Root ".agents\skills"),
    (Join-Path $Root "hosts\openclaw-acpx\skills")
) | ConvertTo-Json -Compress
& openclaw config set skills.load.extraDirs $SkillDirs --strict-json
& openclaw config set skills.load.watch true --strict-json

if ($Restart) {
    & openclaw gateway restart
} else {
    Write-Host ""
    Write-Host "Configuration written. Restart when safe:"
    Write-Host "  openclaw gateway restart"
}

Write-Host ""
Write-Host "Verification:"
Write-Host "  openclaw skills list"
Write-Host ""
Write-Host "Then run in an OpenClaw conversation:"
Write-Host "  /acp doctor"
Write-Host ""
Write-Host "Worker smoke tests:"
Write-Host "  /acp spawn codex"
Write-Host "  /acp spawn claude"
Write-Host "  /acp spawn kiro"
Write-Host "  /acp spawn kilocode"
