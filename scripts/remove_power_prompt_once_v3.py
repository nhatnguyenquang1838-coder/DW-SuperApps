#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/remove_power_prompt_once.py"
spec = importlib.util.spec_from_file_location("remove_power_prompt_once", SOURCE)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load one-shot patch module")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_replace = module.replace_required


def replace_with_compatibility_override(text: str, old: str, new: str, label: str) -> str:
    if label != "dw_workspace_dist host guidance":
        return original_replace(text, old, new, label)
    obsolete = r'''Generate a host-neutral prompt:

`dw power prompt <power> --system <system> --task \"<task>\"`
'''
    activation = '''## Power activation routing

When a registered Power skill or native alias is selected, load its canonical installed entrypoint and apply it directly to the user's request.

Do not generate a shell command, exported prompt, or copy-and-paste handoff to activate a Power.
'''
    return original_replace(text, obsolete, activation, label)


module.replace_required = replace_with_compatibility_override
module.main()

for relative in (
    ".github/workflows/remove-power-prompt-pr-v2.yml",
    ".github/workflows/remove-power-prompt-pr-v3.yml",
    "scripts/remove_power_prompt_once_v2.py",
    "scripts/remove_power_prompt_once_v3.py",
):
    (ROOT / relative).unlink(missing_ok=True)
