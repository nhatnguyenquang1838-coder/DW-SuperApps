#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASH_BIN="$(command -v bash)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/py" <<'EOF'
#!/bin/sh
if [ "$1" = "-3" ] && [ "$2" = "--version" ]; then
  printf 'Python 3.13.0\n'
  exit 0
fi
printf 'py-launcher:%s\n' "$*"
EOF
chmod +x "$TMP/py"

output="$(PATH="$TMP" "$BASH_BIN" -c '
  source "$1"
  dw_python_init
  python3 --version
  python --version
  py -3 --version
  dw_kiro_python --version
' _ "$ROOT/scripts/python-resolver.sh")"

expected="Python 3.13.0"
[[ "$(printf '%s\n' "$output" | sed -n '2p')" == "$expected" ]]
[[ "$(printf '%s\n' "$output" | sed -n '3p')" == "$expected" ]]
[[ "$(printf '%s\n' "$output" | sed -n '4p')" == "$expected" ]]
[[ "$(printf '%s\n' "$output" | sed -n '5p')" == "$expected" ]]

cat > "$TMP/broken-python" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod +x "$TMP/broken-python"
set +e
DW_PYTHON_BIN="$TMP/broken-python" "$BASH_BIN" -c '
  source "$1"
  dw_python_init
' _ "$ROOT/scripts/python-resolver.sh" >/dev/null 2>&1
status=$?
set -e
[[ "$status" -eq 127 ]]

cat > "$TMP/python2" <<'EOF'
#!/bin/sh
printf 'Python 2.7.18\n'
EOF
chmod +x "$TMP/python2"
set +e
DW_PYTHON_BIN="$TMP/python2" "$BASH_BIN" -c '
  source "$1"
  dw_python_init
' _ "$ROOT/scripts/python-resolver.sh" >/dev/null 2>&1
status=$?
set -e
[[ "$status" -eq 127 ]]

bash -n "$ROOT/scripts/python-resolver.sh" \
  "$ROOT/.kiro/skills/dw-power-installation/scripts/python-session.sh"
echo "PASS: Kiro Python session resolver"
