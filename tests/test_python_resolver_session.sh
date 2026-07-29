#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASH_BIN="$(command -v bash)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/py" <<'EOF'
#!/bin/sh
printf 'py-launcher:%s\n' "$*"
EOF
chmod +x "$TMP/py"

output="$(PATH="$TMP" "$BASH_BIN" -c '
  source "$1"
  dw_python_session_init
  python3 --version
  python --version
  py -3 --version
  dw_kiro_python --version
' _ "$ROOT/scripts/python-resolver.sh")"

expected="py-launcher:-3 --version"
[[ "$(printf '%s\n' "$output" | sed -n '2p')" == "$expected" ]]
[[ "$(printf '%s\n' "$output" | sed -n '3p')" == "$expected" ]]
[[ "$(printf '%s\n' "$output" | sed -n '4p')" == "$expected" ]]
[[ "$(printf '%s\n' "$output" | sed -n '5p')" == "$expected" ]]

bash -n "$ROOT/scripts/python-resolver.sh" \
  "$ROOT/.kiro/skills/dw-power-installation/scripts/python-session.sh"
echo "PASS: Kiro Python session resolver"
