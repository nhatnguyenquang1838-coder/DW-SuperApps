$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
python (Join-Path $Root "scripts/dw_cli.py") @args
exit $LASTEXITCODE
