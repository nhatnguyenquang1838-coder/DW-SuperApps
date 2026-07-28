param(
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$Profile,

    [switch]$Restart,

    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if ($VerifyOnly -and $Restart) {
    throw "-VerifyOnly cannot be combined with -Restart."
}

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
    throw "Python 3 is required to generate adapters and verify JSON config."
}

$OpenClawPrefix = @()
if ($Profile) {
    $OpenClawPrefix = @("--profile", $Profile)
}

function Invoke-OpenClaw {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & openclaw @OpenClawPrefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw command failed: openclaw $($OpenClawPrefix -join ' ') $($Arguments -join ' ')"
    }
}

function Get-OpenClawOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $Output = @(Invoke-OpenClaw -Arguments $Arguments)
    return ($Output -join [Environment]::NewLine).Trim()
}

function Assert-ConfigJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedJson
    )

    $ActualJson = Get-OpenClawOutput -Arguments @("config", "get", $Path, "--json")
    $Actual = $ActualJson | ConvertFrom-Json
    $Expected = $ExpectedJson | ConvertFrom-Json

    $ActualNormalized = $Actual | ConvertTo-Json -Compress -Depth 20
    $ExpectedNormalized = $Expected | ConvertTo-Json -Compress -Depth 20

    if ($ActualNormalized -ne $ExpectedNormalized) {
        throw "Config mismatch for ${Path}: expected=${ExpectedNormalized} actual=${ActualNormalized}"
    }

    Write-Host "  PASS $Path = $ActualJson"
}

$SkillDirs = @(
    (Join-Path $Root ".agents\skills"),
    (Join-Path $Root "hosts\openclaw-acpx\skills")
) | ConvertTo-Json -Compress

if (-not $VerifyOnly) {
    if ($Python -eq "py") {
        & py -3 (Join-Path $Root "scripts\dw_cli.py") host install custom --mode wrapper
    } else {
        & python (Join-Path $Root "scripts\dw_cli.py") host install custom --mode wrapper
    }
    if ($LASTEXITCODE -ne 0) {
        throw "DW Power adapter generation failed."
    }

    Invoke-OpenClaw -Arguments @("plugins", "install", "@openclaw/acpx")
    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.enabled", "true", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "acp.enabled", "true", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "acp.dispatch.enabled", "true", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "acp.backend", "acpx")
    Invoke-OpenClaw -Arguments @("config", "set", "acp.defaultAgent", "codex")
    Invoke-OpenClaw -Arguments @("config", "set", "acp.allowedAgents", '["codex","claude","kiro","kilocode"]', "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "acp.stream.deliveryMode", "live")

    Invoke-OpenClaw -Arguments @("config", "set", "session.threadBindings.enabled", "true", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "session.threadBindings.idleHours", "24", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "session.threadBindings.maxAgeHours", "0", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "session.threadBindings.spawnSessions", "true", "--strict-json")

    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.config.permissionMode", "approve-reads")
    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.config.nonInteractivePermissions", "fail")
    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.config.probeAgent", "codex")
    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.config.timeoutSeconds", "120", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.config.pluginToolsMcpBridge", "false", "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "plugins.entries.acpx.config.openClawToolsMcpBridge", "false", "--strict-json")

    Invoke-OpenClaw -Arguments @("config", "set", "skills.load.extraDirs", $SkillDirs, "--strict-json")
    Invoke-OpenClaw -Arguments @("config", "set", "skills.load.watch", "true", "--strict-json")
} else {
    Write-Host "Verification-only mode: no adapters, plugins, or config values will be written."
}

$ProfileLabel = if ($Profile) { $Profile } else { "default" }
$ConfigPath = Get-OpenClawOutput -Arguments @("config", "file")

Write-Host ""
Write-Host "OpenClaw profile: $ProfileLabel"
Write-Host "Config file: $ConfigPath"
Write-Host "Validating config..."
Invoke-OpenClaw -Arguments @("config", "validate")

Write-Host "Reading back governed ACPX settings..."
Assert-ConfigJson -Path "plugins.entries.acpx.enabled" -ExpectedJson "true"
Assert-ConfigJson -Path "acp.enabled" -ExpectedJson "true"
Assert-ConfigJson -Path "acp.dispatch.enabled" -ExpectedJson "true"
Assert-ConfigJson -Path "acp.backend" -ExpectedJson '"acpx"'
Assert-ConfigJson -Path "acp.defaultAgent" -ExpectedJson '"codex"'
Assert-ConfigJson -Path "acp.allowedAgents" -ExpectedJson '["codex","claude","kiro","kilocode"]'
Assert-ConfigJson -Path "session.threadBindings.enabled" -ExpectedJson "true"
Assert-ConfigJson -Path "session.threadBindings.idleHours" -ExpectedJson "24"
Assert-ConfigJson -Path "session.threadBindings.maxAgeHours" -ExpectedJson "0"
Assert-ConfigJson -Path "session.threadBindings.spawnSessions" -ExpectedJson "true"
Assert-ConfigJson -Path "plugins.entries.acpx.config.permissionMode" -ExpectedJson '"approve-reads"'
Assert-ConfigJson -Path "plugins.entries.acpx.config.nonInteractivePermissions" -ExpectedJson '"fail"'
Assert-ConfigJson -Path "plugins.entries.acpx.config.probeAgent" -ExpectedJson '"codex"'
Assert-ConfigJson -Path "plugins.entries.acpx.config.timeoutSeconds" -ExpectedJson "120"
Assert-ConfigJson -Path "plugins.entries.acpx.config.pluginToolsMcpBridge" -ExpectedJson "false"
Assert-ConfigJson -Path "plugins.entries.acpx.config.openClawToolsMcpBridge" -ExpectedJson "false"
Assert-ConfigJson -Path "skills.load.extraDirs" -ExpectedJson $SkillDirs
Assert-ConfigJson -Path "skills.load.watch" -ExpectedJson "true"

if ($Restart) {
    Invoke-OpenClaw -Arguments @("gateway", "restart")
} else {
    Write-Host ""
    Write-Host "Gateway was not restarted. Restart when safe:"
    if ($Profile) {
        Write-Host "  openclaw --profile $Profile gateway restart"
    } else {
        Write-Host "  openclaw gateway restart"
    }
}

Write-Host ""
Write-Host "Verification completed for profile: $ProfileLabel"
Write-Host ""
Write-Host "Read config again without writing:"
if ($Profile) {
    Write-Host "  openclaw --profile $Profile config file"
    Write-Host "  openclaw --profile $Profile config validate"
    Write-Host "  .\hosts\openclaw-acpx\install.ps1 -Profile $Profile -VerifyOnly"
} else {
    Write-Host "  openclaw config file"
    Write-Host "  openclaw config validate"
    Write-Host "  .\hosts\openclaw-acpx\install.ps1 -VerifyOnly"
}
Write-Host ""
Write-Host "Then run in an OpenClaw conversation:"
Write-Host "  /acp doctor"
Write-Host ""
Write-Host "Worker smoke tests:"
Write-Host "  /acp spawn codex"
Write-Host "  /acp spawn claude"
Write-Host "  /acp spawn kiro"
Write-Host "  /acp spawn kilocode"
