#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/bin/dw"
BIN_DIR="${HOME:?HOME is required}/.local/bin"
LAUNCHER="$BIN_DIR/dw"
LAUNCHER_MARKER="# generated-by: DW-SuperApps installer"
PROFILE_START="# >>> DW SuperApps CLI >>>"
PROFILE_END="# <<< DW SuperApps CLI <<<"

usage() {
  cat <<'EOF'
Usage:
  ./bin/dw install [--shell auto|bash|zsh|all|none] [--force] [--init]
  ./bin/dw uninstall [--shell auto|bash|zsh|all|none] [--force]
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
    --force) FORCE=1; shift ;;
    --init) RUN_INIT=1; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

case "$ACTION" in
  install|uninstall) ;;
  *) echo "ERROR: unknown action: $ACTION" >&2; usage; exit 2 ;;
esac

case "$SHELL_MODE" in
  auto|bash|zsh|all|none) ;;
  *) echo "ERROR: unsupported shell: $SHELL_MODE" >&2; exit 2 ;;
esac

resolve_shell_mode() {
  if [[ "$SHELL_MODE" != "auto" ]]; then
    printf '%s\n' "$SHELL_MODE"
    return
  fi
  case "${SHELL##*/}" in
    zsh) printf '%s\n' zsh ;;
    *) printf '%s\n' bash ;;
  esac
}

PROFILES=()
case "$(resolve_shell_mode)" in
  bash) PROFILES+=("$HOME/.bashrc") ;;
  zsh) PROFILES+=("$HOME/.zshrc") ;;
  all) PROFILES+=("$HOME/.bashrc" "$HOME/.zshrc") ;;
  none) ;;
esac

strip_profile_block() {
  local profile="$1"
  local output="$2"
  awk -v start="$PROFILE_START" -v end="$PROFILE_END" '
    $0 == start { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { print }
  ' "$profile" > "$output"
}

write_profile_block() {
  local profile="$1"
  local tmp
  mkdir -p "$(dirname "$profile")"
  touch "$profile"
  tmp="$(mktemp "${profile}.dw.XXXXXX")"
  strip_profile_block "$profile" "$tmp"
  {
    cat "$tmp"
    printf '\n%s\n' "$PROFILE_START"
    printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"'
    printf '%s\n' "$PROFILE_END"
  } > "$profile"
  rm -f "$tmp"
  echo "PROFILE: $profile"
}

remove_profile_block() {
  local profile="$1"
  local tmp
  [[ -f "$profile" ]] || return 0
  tmp="$(mktemp "${profile}.dw.XXXXXX")"
  strip_profile_block "$profile" "$tmp"
  mv "$tmp" "$profile"
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
