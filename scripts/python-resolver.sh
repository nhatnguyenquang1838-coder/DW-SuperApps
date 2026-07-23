#!/usr/bin/env bash

# Shared Python launcher for Bash entrypoints.
# Resolution order: explicit DW_PYTHON, python3, python, Windows py -3.

dw_python_error() {
  echo "ERROR: Python 3 was not found." >&2
  echo "Install Python 3 or set DW_PYTHON to an executable path." >&2
  return 127
}

dw_python() {
  if [[ -n "${DW_PYTHON:-}" ]]; then
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
  if [[ -n "${DW_PYTHON:-}" ]]; then
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
