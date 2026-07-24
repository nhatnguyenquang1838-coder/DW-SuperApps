$ErrorActionPreference = "Stop"
$DistRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { throw "Python 3 is required" }
if ($Python -eq "py") {
  & py -3 (Join-Path $DistRoot "lib/bootstrap_bmad.py") @args
} else {
  & python (Join-Path $DistRoot "lib/bootstrap_bmad.py") @args
}
exit $LASTEXITCODE
