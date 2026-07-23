#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-check}"
TARGET="${2:-all}"
exec python3 "$ROOT/scripts/dw_cli.py" power "$MODE" "$TARGET"
