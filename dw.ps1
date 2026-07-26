$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
python (Join-Path $Root "scripts/dw_dispatch.py") @args
exit $LASTEXITCODE
