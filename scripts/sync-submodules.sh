#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-check}"
TARGET="${2:-all}"

usage() {
  cat <<'EOF'
Usage: scripts/sync-submodules.sh <mode> [target]

Modes:
  init      Initialize all configured submodules recursively.
  check     Show current pins, branch drift, and dirty state. Default.
  update    Fetch and checkout each configured remote branch tip.
  pin       Stage changed gitlinks and .gitmodules for review; does not commit.
  status    Show concise git submodule status.

Targets:
  all | powers | systems | gwc | ua | task-me | rental-home

Examples:
  scripts/sync-submodules.sh init
  scripts/sync-submodules.sh check powers
  scripts/sync-submodules.sh update task-me
  scripts/sync-submodules.sh pin all
EOF
}

cd "$ROOT"

map_target() {
  case "$TARGET" in
    all) printf '%s\n' powers/gwc powers/ua powers/task-me systems/rental-home ;;
    powers) printf '%s\n' powers/gwc powers/ua powers/task-me ;;
    systems) printf '%s\n' systems/rental-home ;;
    gwc) printf '%s\n' powers/gwc ;;
    ua) printf '%s\n' powers/ua ;;
    task-me) printf '%s\n' powers/task-me ;;
    rental-home) printf '%s\n' systems/rental-home ;;
    *) echo "Unknown target: $TARGET" >&2; usage; exit 2 ;;
  esac
}

readarray -t PATHS < <(map_target)

require_initialized() {
  local path="$1"
  if [[ ! -d "$path/.git" && ! -f "$path/.git" ]]; then
    echo "ERROR: $path is not initialized. Run: scripts/sync-submodules.sh init" >&2
    return 1
  fi
}

case "$MODE" in
  init)
    git submodule sync --recursive
    git submodule update --init --recursive
    ;;

  status)
    git submodule status --recursive
    ;;

  check)
    failed=0
    for path in "${PATHS[@]}"; do
      require_initialized "$path" || { failed=1; continue; }
      pinned="$(git ls-tree HEAD "$path" | awk '{print $3}')"
      current="$(git -C "$path" rev-parse HEAD)"
      branch="$(git config -f .gitmodules --get "submodule.$path.branch" 2>/dev/null || echo main)"
      git -C "$path" fetch --quiet origin "$branch" || true
      remote="$(git -C "$path" rev-parse "origin/$branch" 2>/dev/null || echo unavailable)"
      dirty="clean"
      [[ -n "$(git -C "$path" status --porcelain)" ]] && dirty="DIRTY"
      relation="pinned"
      [[ "$current" != "$pinned" ]] && relation="working-copy-moved"
      [[ "$remote" != "unavailable" && "$current" != "$remote" ]] && relation="$relation,remote-drift"
      printf '%-24s pin=%s current=%s remote=%s state=%s %s\n' \
        "$path" "${pinned:0:12}" "${current:0:12}" "${remote:0:12}" "$relation" "$dirty"
      [[ "$dirty" == "DIRTY" ]] && failed=1
    done
    exit "$failed"
    ;;

  update)
    for path in "${PATHS[@]}"; do
      require_initialized "$path"
      if [[ -n "$(git -C "$path" status --porcelain)" ]]; then
        echo "ERROR: refusing to update dirty submodule $path" >&2
        exit 1
      fi
      branch="$(git config -f .gitmodules --get "submodule.$path.branch" 2>/dev/null || echo main)"
      echo "Updating $path -> origin/$branch"
      git -C "$path" fetch origin "$branch"
      git -C "$path" checkout --detach "origin/$branch"
    done
    echo "Updated working copies. Review with: scripts/sync-submodules.sh check $TARGET"
    echo "Stage pins with: scripts/sync-submodules.sh pin $TARGET"
    ;;

  pin)
    for path in "${PATHS[@]}"; do
      require_initialized "$path"
      if [[ -n "$(git -C "$path" status --porcelain)" ]]; then
        echo "ERROR: refusing to pin dirty submodule $path" >&2
        exit 1
      fi
      git add "$path"
    done
    git add .gitmodules
    echo "Pins staged. No commit was created."
    git diff --cached --submodule=short
    ;;

  -h|--help|help)
    usage
    ;;

  *)
    echo "Unknown mode: $MODE" >&2
    usage
    exit 2
    ;;
esac
