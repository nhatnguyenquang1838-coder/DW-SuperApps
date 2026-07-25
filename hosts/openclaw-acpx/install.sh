#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESTART=0

for arg in "$@"; do
  case "$arg" in
    --restart) RESTART=1 ;;
    --help|-h)
      cat <<'EOF'
Usage: hosts/openclaw-acpx/install.sh [--restart]

Installs the official OpenClaw ACPX plugin, enables governed ACP dispatch,
registers Codex, Claude, Kiro, and Kilocode, and loads DW SUPER skills.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

command -v openclaw >/dev/null 2>&1 || {
  echo "ERROR: openclaw is not available on PATH." >&2
  exit 1
}

PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: Python 3 is required to generate DW Power adapters." >&2
  exit 1
fi

"$PYTHON_BIN" "$ROOT/scripts/dw_cli.py" host install custom --mode wrapper

openclaw plugins install @openclaw/acpx
openclaw config set plugins.entries.acpx.enabled true --strict-json
openclaw config set acp.enabled true --strict-json
openclaw config set acp.dispatch.enabled true --strict-json
openclaw config set acp.backend acpx
openclaw config set acp.defaultAgent codex
openclaw config set acp.allowedAgents '["codex","claude","kiro","kilocode"]' --strict-json
openclaw config set acp.stream.deliveryMode live

openclaw config set session.threadBindings.enabled true --strict-json
openclaw config set session.threadBindings.idleHours 24 --strict-json
openclaw config set session.threadBindings.maxAgeHours 0 --strict-json
openclaw config set session.threadBindings.spawnSessions true --strict-json

openclaw config set plugins.entries.acpx.config.permissionMode approve-reads
openclaw config set plugins.entries.acpx.config.nonInteractivePermissions fail
openclaw config set plugins.entries.acpx.config.probeAgent codex
openclaw config set plugins.entries.acpx.config.timeoutSeconds 120 --strict-json
openclaw config set plugins.entries.acpx.config.pluginToolsMcpBridge false --strict-json
openclaw config set plugins.entries.acpx.config.openClawToolsMcpBridge false --strict-json

SKILL_DIRS="$(printf '["%s/.agents/skills","%s/hosts/openclaw-acpx/skills"]' "$ROOT" "$ROOT")"
openclaw config set skills.load.extraDirs "$SKILL_DIRS" --strict-json
openclaw config set skills.load.watch true --strict-json

if [[ "$RESTART" -eq 1 ]]; then
  openclaw gateway restart
else
  echo
  echo "Configuration written. Restart when safe:"
  echo "  openclaw gateway restart"
fi

cat <<'EOF'

Verification:
  openclaw skills list

Then run this command in an OpenClaw conversation:
  /acp doctor

Worker smoke tests:
  /acp spawn codex
  /acp spawn claude
  /acp spawn kiro
  /acp spawn kilocode
EOF
