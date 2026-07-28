#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/remove_power_prompt_once_v4.py"
text = SCRIPT.read_text(encoding="utf-8")
replacements = {
    'text = setup.read_text(encoding="utf-8")n\n': 'text = setup.read_text(encoding="utf-8")\n',
    '''active_files: list[Path] = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
]
''': '''active_files: list[Path] = [
    candidate
    for candidate in (
        ROOT / "AGENTS.md",
        ROOT / "README.md",
        ROOT / "CLAUDE.md",
    )
    if candidate.is_file()
]
''',
    '''for candidate in active_files:
    try:
''': '''for candidate in active_files:
    if candidate.name.startswith("remove_power_prompt_once"):
        continue
    try:
''',
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit(f"cannot locate v4 patch target: {old.splitlines()[0]}")
    text = text.replace(old, new)
SCRIPT.write_text(text, encoding="utf-8")
runpy.run_path(str(SCRIPT), run_name="__main__")
