#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p .kiro/skills .codex/skills

link_skill() {
  local host="$1"
  local power="$2"
  local source=""
  local destination=".$host/skills/$power"

  if [[ -f "powers/$power/SKILL.md" ]]; then
    source="../../powers/$power"
  elif [[ -d "powers/$power/.$host/skills/$power" ]]; then
    source="../../../powers/$power/.$host/skills/$power"
  elif [[ -d "powers/$power/.kiro/skills/$power" ]]; then
    source="../../../powers/$power/.kiro/skills/$power"
  else
    echo "SKIP: no portable skill entrypoint found for $power on $host"
    return 0
  fi

  if [[ -e "$destination" && ! -L "$destination" ]]; then
    echo "ERROR: refusing to replace non-symlink $destination" >&2
    return 1
  fi

  rm -f "$destination"
  ln -s "$source" "$destination"
  echo "LINK: $destination -> $source"
}

for power in gwc ua task-me; do
  link_skill kiro "$power"
  link_skill codex "$power"
done

cat > .kiro/skills/README.generated.md <<'EOF'
# Generated Kiro Power Links

Run `bin/dw host install` after cloning or updating Power submodules. Do not edit generated symlinks; canonical behavior remains in `powers/`.
EOF

cat > .codex/skills/README.generated.md <<'EOF'
# Generated Codex Power Links

Run `bin/dw host install` after cloning or updating Power submodules. Do not edit generated symlinks; canonical behavior remains in `powers/`.
EOF

echo "Host adapter installation complete."
