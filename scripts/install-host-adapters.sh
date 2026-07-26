#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-all}"
shift || true
exec "$ROOT/bin/dw" host install "$HOST" "$@"
