#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/remove_power_prompt_once.py"
text = SCRIPT.read_text(encoding="utf-8")
old = '''    text = replace_required(text, old_host, new_host, "dw_workspace_dist host guidance")
    write(path, text)
'''
new = r'''    old_host_dist = r\'''## Routing

1. Resolve the target system from `workspace.yaml`.
2. Load Power code from the workspace distribution store first.
3. Use source submodules only as an explicit compatibility fallback.
4. Keep runtime and project configuration inside the selected system repository.
5. Keep packages, inbox, history, bindings, router, and all host adapters in DW-SuperApps.
6. Never install Power skill payloads into a registered system.
{orchestration_section}
Generate a host-neutral prompt:

`dw power prompt <power> --system <system> --task \\"<task>\\"`
\'''
    new_host_dist = \'''## Routing

1. Resolve the target system from `workspace.yaml`.
2. Load Power code from the workspace distribution store first.
3. Use source submodules only as an explicit compatibility fallback.
4. Keep runtime and project configuration inside the selected system repository.
5. Keep packages, inbox, history, bindings, router, and all host adapters in DW-SuperApps.
6. Never install Power skill payloads into a registered system.
{orchestration_section}
\''' + host_activation
    text = replace_required(
        text,
        old_host_dist,
        new_host_dist,
        "dw_workspace_dist host guidance",
    )
    write(path, text)
'''
if old not in text:
    raise SystemExit("cannot patch v1 compatibility guidance")
SCRIPT.write_text(text.replace(old, new), encoding="utf-8")
runpy.run_path(str(SCRIPT), run_name="__main__")
for relative in (
    ".github/workflows/remove-power-prompt-pr-v2.yml",
    "scripts/remove_power_prompt_once_v2.py",
):
    (ROOT / relative).unlink(missing_ok=True)
