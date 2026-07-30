#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -P "$SCRIPT_DIR/.." && pwd)"

TASK_ID="${1:-}"
if [[ -z "$TASK_ID" ]]; then
  echo "Usage: gwc_post_gate.sh <task-id>" >&2
  exit 1
fi

echo "Regenerating GWC HTML report for task: $TASK_ID"

# shellcheck source=./python-resolver.sh
source "$ROOT/scripts/python-resolver.sh"
dw_exec_python "$ROOT/scripts/gwc_report.py" "$TASK_ID" --workspace "$ROOT"