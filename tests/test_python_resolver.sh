#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASH_BIN="$(command -v bash)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/python" <<'EOF'
#!/bin/sh
printf 'python-fallback:%s\n' "$*"
EOF
chmod +x "$TMP/python"

output="$(PATH="$TMP" "$BASH_BIN" -c 'source "$1"; dw_python --version' _ "$ROOT/scripts/python-resolver.sh")"
[[ "$output" == "python-fallback:--version" ]]

cat > "$TMP/custom-python" <<'EOF'
#!/bin/sh
printf 'custom-python:%s\n' "$*"
EOF
chmod +x "$TMP/custom-python"

output="$(PATH="$TMP" DW_PYTHON="$TMP/custom-python" "$BASH_BIN" -c 'source "$1"; dw_python -c test' _ "$ROOT/scripts/python-resolver.sh")"
[[ "$output" == "custom-python:-c test" ]]

mkdir "$TMP/empty"
set +e
PATH="$TMP/empty" "$BASH_BIN" -c 'source "$1"; dw_python --version' _ "$ROOT/scripts/python-resolver.sh" >/dev/null 2>&1
status=$?
set -e
[[ "$status" -eq 127 ]]

bash -n "$ROOT/bin/dw" "$ROOT/scripts/install-dw.sh" "$ROOT/scripts/python-resolver.sh"
echo "PASS: Python resolver"
