#!/usr/bin/env bash

# Compatibility entrypoint for Kiro/Git Bash. Source it in the active session.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/python-resolver.sh"
dw_python_session_init

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "ERROR: source this file in the active Kiro Bash session." >&2
  exit 2
fi
