#!/usr/bin/env bash

# Kiro/Git Bash session bootstrap. Source this file; do not execute it in a child shell.

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPER_PROJECT_ROOT="$(cd "$SKILL_ROOT/../../.." && pwd)"

# shellcheck source=../../../../scripts/python-resolver.sh
source "$SUPER_PROJECT_ROOT/scripts/python-resolver.sh"
dw_python_session_init

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "ERROR: source this file in the active Kiro Bash session." >&2
  exit 2
fi
