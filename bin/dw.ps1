$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
python (Join-Path $Root "scripts/dw_cli.py") @args
exit $LASTEXITCODE
