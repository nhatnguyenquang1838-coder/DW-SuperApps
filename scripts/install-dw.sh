#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/bin/dw"
BIN_DIR="${HOME:?HOME is required}/.local/bin"
LAUNCHER="$BIN_DIR/dw"
LAUNCHER_MARKER="# generated-by: DW-SuperApps installer"
PROFILE_START="# >>> DW SuperApps CLI >>>"
PROFILE_END="# <<< DW SuperApps CLI <<<"

# shellcheck source=python-resolver.sh
source "$ROOT/scripts/python-resolver.sh"

usage() {
  cat <<'EOF'
Usage:
  ./bin/dw install [--shell auto|bash|zsh|all|none] [--force] [--init]
  ./bin/dw uninstall [--shell auto|bash|zsh|all|none] [--force]

Examples:
  ./bin/dw install
  ./bin/dw install --shell bash --init
  ./bin/dw install --shell zsh
  ./bin/dw uninstall
EOF
}

ACTION="${1:-install}"
shift || true
SHELL_MODE="auto"
FORCE=0
RUN_INIT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --shell)
      [[ $# -ge 2 ]] || { echo "ERROR: --shell requires a value" >&2; exit 2; }
      SHELL_MODE="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --init)
      RUN_INIT=1
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

case "$ACTION" in
  install|uninstall) ;;
  *)
    echo "ERROR: unknown action: $ACTION" >&2
    usage
    exit 2
    ;;
esac

case "$SHELL_MODE" in
  auto|bash|zsh|all|none) ;;
  *)
    echo "ERROR: unsupported shell: $SHELL_MODE" >&2
    exit 2
    ;;
esac

select_profiles() {
  local mode="$SHELL_MODE"
  if [[ "$mode" == "auto" ]]; then
    case "${SHELL##*/}" in
      zsh) mode="zsh" ;;
      *) mode="bash" ;;
    esac
  fi

  case "$mode" in
    bash) printf '%s\n' "$HOME/.bashrc" ;;
    zsh) printf '%s\n' "$HOME/.zshrc" ;;
    all) printf '%s\n' "$HOME/.bashrc" "$HOME/.zshrc" ;;
    none) return 0 ;;
  esac
}

write_profile_block() {
  local profile="$1"
  mkdir -p "$(dirname "$profile")"
  touch "$profile"
  dw_python - "$profile" "$PROFILE_START" "$PROFILE_END" <<'PY'
from pathlib import Path
import sys

profile = Path(sys.argv[1])
start = sys.argv[2]
end = sys.argv[3]
block = f'{start}\nexport PATH="$HOME/.local/bin:$PATH"\n{end}'
text = profile.read_text(encoding="utf-8")

start_at = text.find(start)
if start_at >= 0:
    end_at = text.find(end, start_at)
    if end_at < 0:
        raise SystemExit(f"ERROR: malformed managed block in {profile}")
    end_at += len(end)
    prefix = text[:start_at].rstrip()
    suffix = text[end_at:].lstrip("\n")
    parts = [part for part in (prefix, block, suffix.rstrip()) if part]
    updated = "\n\n".join(parts) + "\n"
else:
    updated = text.rstrip()
    if updated:
        updated += "\n\n"
    updated += block + "\n"

profile.write_text(updated, encoding="utf-8")
PY
  echo "PROFILE: $profile"
}

remove_profile_block() {
  local profile="$1"
  [[ -f "$profile" ]] || return 0
  dw_python - "$profile" "$PROFILE_START" "$PROFILE_END" <<'PY'
from pathlib import Path
import sys

profile = Path(sys.argv[1])
start = sys.argv[2]
end = sys.argv[3]
text = profile.read_text(encoding="utf-8")
start_at = text.find(start)
if start_at < 0:
    raise SystemExit(0)
end_at = text.find(end, start_at)
if end_at < 0:
    raise SystemExit(f"ERROR: malformed managed block in {profile}")
end_at += len(end)
prefix = text[:start_at].rstrip()
suffix = text[end_at:].lstrip("\n")
parts = [part for part in (prefix, suffix.rstrip()) if part]
updated = "\n\n".join(parts)
if updated:
    updated += "\n"
profile.write_text(updated, encoding="utf-8")
PY
  echo "PROFILE CLEAN: $profile"
}

install_launcher() {
  mkdir -p "$BIN_DIR"
  chmod +x "$TARGET"

  if [[ -e "$LAUNCHER" || -L "$LAUNCHER" ]]; then
    if [[ -f "$LAUNCHER" ]] && grep -Fq "$LAUNCHER_MARKER" "$LAUNCHER"; then
      :
    elif [[ "$FORCE" -eq 1 ]]; then
      rm -rf "$LAUNCHER"
    else
      echo "ERROR: refusing to replace unmanaged $LAUNCHER; use --force" >&2
      exit 1
    fi
  fi

  {
    echo '#!/usr/bin/env bash'
    echo "$LAUNCHER_MARKER"
    printf 'exec %q "$@"\n' "$TARGET"
  } > "$LAUNCHER"
  chmod +x "$LAUNCHER"
  echo "INSTALLED: $LAUNCHER -> $TARGET"
}

uninstall_launcher() {
  [[ -e "$LAUNCHER" || -L "$LAUNCHER" ]] || return 0
  if [[ -f "$LAUNCHER" ]] && grep -Fq "$LAUNCHER_MARKER" "$LAUNCHER"; then
    rm -f "$LAUNCHER"
  elif [[ "$FORCE" -eq 1 ]]; then
    rm -rf "$LAUNCHER"
  else
    echo "ERROR: refusing to remove unmanaged $LAUNCHER; use --force" >&2
    exit 1
  fi
  echo "REMOVED: $LAUNCHER"
}

mapfile -t PROFILES < <(select_profiles)

if [[ "$ACTION" == "install" ]]; then
  install_launcher
  for profile in "${PROFILES[@]}"; do
    write_profile_block "$profile"
  done
  echo
  echo "DW CLI installed."
  if [[ ${#PROFILES[@]} -gt 0 ]]; then
    echo "Reload your shell or run: source ${PROFILES[0]}"
  else
    echo "Ensure $BIN_DIR is on PATH."
  fi
  echo "Verify with: dw --version"
  if [[ "$RUN_INIT" -eq 1 ]]; then
    echo
    "$TARGET" init all
  fi
else
  uninstall_launcher
  for profile in "${PROFILES[@]}"; do
    remove_profile_block "$profile"
  done
  echo "DW CLI uninstalled. Reload your shell."
fi
