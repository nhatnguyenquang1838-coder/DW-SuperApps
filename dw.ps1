$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
python (Join-Path $Root "scripts/dw_entry.py") @args
exit $LASTEXITCODE
