#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
old = """3. Apply that Power to the user's task in the current conversation.
4. Continue until the task reaches a real capability, evidence, or authority boundary.
"""
new = """3. Apply that Power to the user's task in the current conversation.
4. Keep runtime and project configuration under the target system's `{spec['runtimeDataRoot']}/`.
5. Continue until the task reaches a real capability, evidence, or authority boundary.
"""
for relative in ("scripts/dw_cli.py", "scripts/dw_workspace_dist.py"):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected one activation block in {relative}, found {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8")

for relative in (
    ".github/workflows/fix-power-activation-runtime-root.yml",
    "scripts/fix_power_activation_runtime_root.py",
):
    (ROOT / relative).unlink(missing_ok=True)
