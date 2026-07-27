#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FOUNDATION_REF="${1:-$(git -C "$ROOT" rev-parse HEAD)}"
shift || true
POWER_ARGS=()
if [[ $# -gt 0 ]]; then
  POWER_ARGS=("$@")
fi

echo "=== Building Power distributions ==="
python "$ROOT/scripts/distribution_builder.py" \
  --foundation-ref "$FOUNDATION_REF" \
  "${POWER_ARGS[@]}"

echo
echo "=== Validating staged distributions ==="
python "$ROOT/scripts/distribution_installer.py" \
  --staging "$ROOT/.kilo/staging/power-dist" \
  --store-root "$ROOT/.kilo/staging/power-dist/.store" \
  --target "$ROOT/.kilo/staging/power-dist/.consumer" \
  "${POWER_ARGS[@]}"

echo
echo "=== Distribution build complete ==="
cat "$ROOT/.kilo/staging/power-dist/build-summary.json"
echo
cat "$ROOT/.kilo/staging/power-dist/validation-report.json"
