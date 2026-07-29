#!/usr/bin/env bash

# Shared Python launcher for Bash entrypoints.
# Resolution order: explicit DW_PYTHON, python3, python, Windows py -3.

dw_python_error() {
  echo "ERROR: Python 3 was not found." >&2
  echo "Install Python 3 or set DW_PYTHON_BIN/DW_PYTHON to an executable path." >&2
  return 127
}

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
  if [[ -n "${DW_PYTHON_ARGS:-}" ]]; then
    local -a launcher_args=()
    read -r -a launcher_args <<< "$DW_PYTHON_ARGS"
    command "$launcher" "${launcher_args[@]}" "$@"
  else
    command "$launcher" "$@"
  fi
}

dw_python() {
  if [[ -n "${DW_PYTHON_BIN:-}" ]]; then
    dw_python_with_launcher "$DW_PYTHON_BIN" "$@"
  elif [[ -n "${DW_PYTHON:-}" ]]; then
    command "$DW_PYTHON" "$@"
  elif command -v python3 >/dev/null 2>&1; then
    command python3 "$@"
  elif command -v python >/dev/null 2>&1; then
    command python "$@"
  elif command -v py >/dev/null 2>&1; then
    command py -3 "$@"
  else
    dw_python_error
  fi
}

dw_exec_python() {
  if [[ -n "${DW_PYTHON_BIN:-}" ]]; then
    if [[ -n "${DW_PYTHON_ARGS:-}" ]]; then
      local -a launcher_args=()
      read -r -a launcher_args <<< "$DW_PYTHON_ARGS"
      exec "$DW_PYTHON_BIN" "${launcher_args[@]}" "$@"
    else
      exec "$DW_PYTHON_BIN" "$@"
    fi
  elif [[ -n "${DW_PYTHON:-}" ]]; then
    exec "$DW_PYTHON" "$@"
  elif command -v python3 >/dev/null 2>&1; then
    exec python3 "$@"
  elif command -v python >/dev/null 2>&1; then
    exec python "$@"
  elif command -v py >/dev/null 2>&1; then
    exec py -3 "$@"
  else
    dw_python_error
    exit 127
  fi
}

dw_kiro_python() {
  if [[ -z "${DW_PYTHON_BIN:-}" ]]; then
    dw_python_session_init || return $?
  fi
  dw_python_with_launcher "$DW_PYTHON_BIN" "$@"
}

dw_python_session_init() {
  local candidate=""
  local launcher_args=""

  if [[ -n "${DW_PYTHON_BIN:-}" ]]; then
    candidate="$DW_PYTHON_BIN"
    launcher_args="${DW_PYTHON_ARGS:-}"
  elif [[ -n "${DW_PYTHON:-}" ]]; then
    candidate="$(type -P "$DW_PYTHON" 2>/dev/null || true)"
    [[ -n "$candidate" ]] || candidate="$DW_PYTHON"
  elif type -P python3 >/dev/null 2>&1; then
    candidate="$(type -P python3)"
  elif type -P python >/dev/null 2>&1; then
    candidate="$(type -P python)"
  elif type -P py >/dev/null 2>&1; then
    candidate="$(type -P py)"
    launcher_args="-3"
  fi

  if [[ -z "$candidate" ]]; then
    dw_python_error
    return 127
  fi

  # Fail at bootstrap time instead of allowing a broken shim or Python 2
  # executable to fail later during package verification or project binding.
  dw_python_validate_candidate "$candidate" "$launcher_args" || return $?

  export DW_PYTHON_BIN="$candidate"
  export DW_PYTHON_ARGS="$launcher_args"
  export DW_PYTHON="$candidate"
  export PYTHON="$candidate"
  export PYTHON3="$candidate"
  export PY="$candidate"

  # Bash/Git Bash functions make all three spellings work in this session.
  python3() { dw_kiro_python "$@"; }
  python() { dw_kiro_python "$@"; }
  py() {
    if [[ "${1:-}" == "-3" ]]; then
      shift
    fi
    dw_kiro_python "$@"
  }
  export -f dw_python_with_launcher dw_kiro_python python3 python py

  printf 'PYTHON_SESSION: %s %s\n' "$DW_PYTHON_BIN" "${DW_PYTHON_ARGS:-}"
}

# Explicit name used by Kiro/bootstrap prompts. Keep session initialization
# separate from command execution so callers can fail before touching files.
dw_python_init() {
  dw_python_session_init "$@"
}
