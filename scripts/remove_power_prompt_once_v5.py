#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/remove_power_prompt_once_v4.py"
text = SCRIPT.read_text(encoding="utf-8")
old = 'text = setup.read_text(encoding="utf-8")n\n'
new = 'text = setup.read_text(encoding="utf-8")\n'
if text.count(old) != 1:
    raise SystemExit("cannot locate v4 bootstrap typo")
SCRIPT.write_text(text.replace(old, new), encoding="utf-8")
runpy.run_path(str(SCRIPT), run_name="__main__")
for relative in (
    ".github/workflows/remove-power-prompt-pr-v5.yml",
    "scripts/remove_power_prompt_once_v5.py",
):
    (ROOT / relative).unlink(missing_ok=True)
