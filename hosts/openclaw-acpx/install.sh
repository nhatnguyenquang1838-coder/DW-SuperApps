#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESTART=0
VERIFY_ONLY=0
PROFILE=""

usage() {
  cat <<'EOF'
Usage: hosts/openclaw-acpx/install.sh [--profile <name>] [--restart] [--verify-only]

Installs and configures the official OpenClaw ACPX plugin using only OpenClaw
CLI commands. When --profile is provided, every OpenClaw command targets that
isolated profile. The script validates and reads back the effective config.

Options:
  --profile <name>  Target an OpenClaw profile, for example: gwc
  --restart         Restart the targeted gateway after validation
  --verify-only     Do not write config; validate and read back existing config
  --help, -h        Show this help

Examples:
  bash hosts/openclaw-acpx/install.sh --profile gwc --restart
  bash hosts/openclaw-acpx/install.sh --profile gwc --verify-only
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ "$#" -ge 2 ]] || die "--profile requires a value."
      PROFILE="$2"
      shift 2
      ;;
    --profile=*)
      PROFILE="${1#*=}"
      shift
      ;;
    --restart)
      RESTART=1
      shift
      ;;
    --verify-only)
      VERIFY_ONLY=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

if [[ -n "$PROFILE" && ! "$PROFILE" =~ ^[A-Za-z0-9._-]+$ ]]; then
  die "Invalid profile name '$PROFILE'. Use letters, numbers, dot, underscore, or hyphen."
fi

if [[ "$VERIFY_ONLY" -eq 1 && "$RESTART" -eq 1 ]]; then
  die "--verify-only cannot be combined with --restart."
fi

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
  echo "ERROR: Python 3 is required to generate adapters and verify JSON config." >&2
  exit 1
fi

OPENCLAW_ARGS=()
if [[ -n "$PROFILE" ]]; then
  OPENCLAW_ARGS+=(--profile "$PROFILE")
fi

oc() {
  command openclaw "${OPENCLAW_ARGS[@]}" "$@"
}

PROFILE_LABEL="${PROFILE:-default}"
OPENCLAW_DISPLAY="openclaw"
if [[ -n "$PROFILE" ]]; then
  OPENCLAW_DISPLAY+=" --profile $PROFILE"
fi

SKILL_DIRS="$("$PYTHON_BIN" - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
print(json.dumps([
    str(root / ".agents" / "skills"),
    str(root / "hosts" / "openclaw-acpx" / "skills"),
], separators=(",", ":")))
PY
)"

read_and_validate_config() {
  "$PYTHON_BIN" - "$PROFILE" "$ROOT" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

profile, root_raw = sys.argv[1:3]
root = Path(root_raw)
command = ["openclaw"]
if profile:
    command.extend(["--profile", profile])

def run(*args: str) -> str:
    process = subprocess.run(
        [*command, *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        if process.stdout:
            print(process.stdout, end="")
        if process.stderr:
            print(process.stderr, end="", file=sys.stderr)
        raise SystemExit(
            f"ERROR: OpenClaw command failed ({process.returncode}): "
            + " ".join([*command, *args])
        )
    return process.stdout.strip()

config_path = run("config", "file")
print()
print(f"OpenClaw profile: {profile or 'default'}")
print(f"Config file: {config_path}")
print("Validating config...")
validation = run("config", "validate")
if validation:
    print(validation)

expected = {
    "plugins.entries.acpx.enabled": True,
    "acp.enabled": True,
    "acp.dispatch.enabled": True,
    "acp.backend": "acpx",
    "acp.defaultAgent": "codex",
    "acp.allowedAgents": ["codex", "claude", "kiro", "kilocode"],
    "session.threadBindings.enabled": True,
    "session.threadBindings.idleHours": 24,
    "session.threadBindings.maxAgeHours": 0,
    "session.threadBindings.spawnSessions": True,
    "plugins.entries.acpx.config.permissionMode": "approve-reads",
    "plugins.entries.acpx.config.nonInteractivePermissions": "fail",
    "plugins.entries.acpx.config.probeAgent": "codex",
    "plugins.entries.acpx.config.timeoutSeconds": 120,
    "plugins.entries.acpx.config.pluginToolsMcpBridge": False,
    "plugins.entries.acpx.config.openClawToolsMcpBridge": False,
    "skills.load.extraDirs": [
        str(root / ".agents" / "skills"),
        str(root / "hosts" / "openclaw-acpx" / "skills"),
    ],
    "skills.load.watch": True,
}

print("Reading back governed ACPX settings...")
for path, expected_value in expected.items():
    actual_raw = run("config", "get", path, "--json")
    try:
        actual_value = json.loads(actual_raw)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"ERROR: config get returned invalid JSON for {path}: {actual_raw}"
        ) from error
    if actual_value != expected_value:
        raise SystemExit(
            f"ERROR: config mismatch for {path}: "
            f"expected={json.dumps(expected_value, separators=(',', ':'))} "
            f"actual={json.dumps(actual_value, separators=(',', ':'))}"
        )
    print(f"  PASS {path} = {actual_raw}")
PY
}

if [[ "$VERIFY_ONLY" -eq 0 ]]; then
  "$PYTHON_BIN" "$ROOT/scripts/dw_cli.py" host install custom --mode wrapper

  oc plugins install @openclaw/acpx
  oc config set plugins.entries.acpx.enabled true --strict-json
  oc config set acp.enabled true --strict-json
  oc config set acp.dispatch.enabled true --strict-json
  oc config set acp.backend acpx
  oc config set acp.defaultAgent codex
  oc config set acp.allowedAgents '["codex","claude","kiro","kilocode"]' --strict-json
  oc config set acp.stream.deliveryMode live

  oc config set session.threadBindings.enabled true --strict-json
  oc config set session.threadBindings.idleHours 24 --strict-json
  oc config set session.threadBindings.maxAgeHours 0 --strict-json
  oc config set session.threadBindings.spawnSessions true --strict-json

  oc config set plugins.entries.acpx.config.permissionMode approve-reads
  oc config set plugins.entries.acpx.config.nonInteractivePermissions fail
  oc config set plugins.entries.acpx.config.probeAgent codex
  oc config set plugins.entries.acpx.config.timeoutSeconds 120 --strict-json
  oc config set plugins.entries.acpx.config.pluginToolsMcpBridge false --strict-json
  oc config set plugins.entries.acpx.config.openClawToolsMcpBridge false --strict-json

  oc config set skills.load.extraDirs "$SKILL_DIRS" --strict-json
  oc config set skills.load.watch true --strict-json
else
  echo "Verification-only mode: no adapters, plugins, or config values will be written."
fi

read_and_validate_config

if [[ "$RESTART" -eq 1 ]]; then
  oc gateway restart
else
  echo
  echo "Gateway was not restarted. Restart when safe:"
  echo "  $OPENCLAW_DISPLAY gateway restart"
fi

cat <<EOF

Verification completed for profile: $PROFILE_LABEL

Read config again without writing:
  $OPENCLAW_DISPLAY config file
  $OPENCLAW_DISPLAY config validate
  bash hosts/openclaw-acpx/install.sh${PROFILE:+ --profile $PROFILE} --verify-only

Then run in an OpenClaw conversation:
  /acp doctor

Worker smoke tests:
  /acp spawn codex
  /acp spawn claude
  /acp spawn kiro
  /acp spawn kilocode
EOF
