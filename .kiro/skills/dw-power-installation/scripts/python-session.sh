#!/usr/bin/env bash

# Kiro/Git Bash session bootstrap. Source this file; do not execute it in a child shell.

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPER_PROJECT_ROOT="$(cd "$SKILL_ROOT/../../.." && pwd)"

# Prefer the target Super Project resolver when this skill has been copied into a DW-SuperApps
# checkout. The fallback keeps the shipped skill usable from an extracted release without the
# source checkout or its helper scripts.
if [[ -f "$SUPER_PROJECT_ROOT/scripts/python-resolver.sh" ]]; then
  # shellcheck source=../../../../scripts/python-resolver.sh
  source "$SUPER_PROJECT_ROOT/scripts/python-resolver.sh"
else
  dw_python_validate_candidate() {
    local candidate="$1"
    local launcher_args="${2:-}"
    local version=""
    local -a args=()
    if [[ -n "$launcher_args" ]]; then
      read -r -a args <<< "$launcher_args"
    fi
    if [[ -n "$launcher_args" ]]; then
      if ! version="$(command "$candidate" "${args[@]}" --version 2>&1)"; then
        echo "ERROR: Python launcher failed during session init: $candidate ${launcher_args:-} --version" >&2
        [[ -n "$version" ]] && echo "$version" >&2
        return 127
      fi
    elif ! version="$(command "$candidate" --version 2>&1)"; then
      echo "ERROR: Python launcher failed during session init: $candidate --version" >&2
      [[ -n "$version" ]] && echo "$version" >&2
      return 127
    fi
    if [[ ! "$version" =~ (^|[[:space:]])Python[[:space:]]3([.]|[[:space:]]|$) ]]; then
      echo "ERROR: resolved launcher is not Python 3: $candidate ${launcher_args:-}" >&2
      echo "Reported version: $version" >&2
      return 127
    fi
  }

  dw_python_with_launcher() {
    local launcher="$1"
    shift
    "$launcher" "$@"
  }

  dw_kiro_python() {
    if [[ -n "${DW_PYTHON_BIN:-}" ]]; then
      dw_python_with_launcher "$DW_PYTHON_BIN" ${DW_PYTHON_ARGS:-} "$@"
    elif command -v python3 >/dev/null 2>&1; then
      python3 "$@"
    elif command -v python >/dev/null 2>&1; then
      python "$@"
    elif command -v py >/dev/null 2>&1; then
      py -3 "$@"
    else
      echo "ERROR: Python 3 was not found (tried python3, python, py -3)." >&2
      return 127
    fi
  }

  dw_python_session_init() {
    local launcher="" args=""
    if [[ -n "${DW_PYTHON_BIN:-}" ]]; then
      launcher="$DW_PYTHON_BIN"
      args="${DW_PYTHON_ARGS:-}"
    elif [[ -n "${DW_PYTHON:-}" ]]; then
      launcher="$DW_PYTHON"
    elif command -v python3 >/dev/null 2>&1; then
      launcher="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      launcher="$(command -v python)"
    elif command -v py >/dev/null 2>&1; then
      launcher="$(command -v py)"
      args="-3"
    else
      echo "ERROR: Python 3 was not found (tried python3, python, py -3)." >&2
      return 127
    fi
    dw_python_validate_candidate "$launcher" "$args" || return $?
    export DW_PYTHON_BIN="$launcher" DW_PYTHON_ARGS="$args"
    export DW_PYTHON="$launcher" PYTHON="$launcher" PYTHON3="$launcher" PY="$launcher"
    python3() { dw_python_with_launcher "$DW_PYTHON_BIN" ${DW_PYTHON_ARGS:-} "$@"; }
    python() { dw_python_with_launcher "$DW_PYTHON_BIN" ${DW_PYTHON_ARGS:-} "$@"; }
    py() { dw_python_with_launcher "$DW_PYTHON_BIN" ${DW_PYTHON_ARGS:-} "$@"; }
    export -f python3 python py 2>/dev/null || true
    echo "PYTHON_SESSION: $DW_PYTHON_BIN ${DW_PYTHON_ARGS:-}" >&2
  }

  dw_python_init() {
    dw_python_session_init "$@"
  }
fi

dw_python_init

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "ERROR: source this file in the active Kiro Bash session." >&2
  exit 2
fi
