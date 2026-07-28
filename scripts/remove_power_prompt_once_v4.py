#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import re
import shutil
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
try:
    module.main()
except SystemExit as exc:
    if not str(exc).startswith("active references remain:"):
        raise

# Remove the dispatcher fallback that could still execute the deleted command.
dispatch = ROOT / "scripts/dw_dispatch.py"
text = dispatch.read_text(encoding="utf-8")
old_dispatch = '''        if argv[1] == "prompt":
            return distribution_main(argv)
'''
if text.count(old_dispatch) != 1:
    raise SystemExit("expected one dw_dispatch prompt route")
dispatch.write_text(text.replace(old_dispatch, ""), encoding="utf-8")

# Replace the multiline setup guide section.
setup = ROOT / "docs/DW_SUPER_SETUP.md"
text = setup.read_text(encoding="utf-8")n
pattern = re.compile(
    r"## 5\. Generate Power prompts\n.*?(?=Useful discovery commands:)",
    re.S,
)
replacement = '''## 5. Activate Powers natively

Open the DW-SuperApps workspace in a configured host and invoke the native skill alias directly:

```text
/dw-gwc Recover the current governed task state and execute the next authorized gate
/dw-ua Refresh the Rental Home architecture and codebase knowledge graph
/dw-task-me Create an implementation plan with impact analysis for OPS-LEASE
/dw-bmad Refine the product specification
```

The host resolves the target system and canonical installed entrypoint. No generated prompt or terminal activation command is required.

'''
text, count = pattern.subn(replacement, text)
if count != 1:
    raise SystemExit(f"expected one DW_SUPER_SETUP prompt section, found {count}")
setup.write_text(text, encoding="utf-8")

# Replace Kiro and Codex examples in the runtime guide.
runtime = ROOT / "docs/POWER_RUNTIME_V2.md"
text = runtime.read_text(encoding="utf-8")
kiro = re.compile(
    r"Open the `DW-SuperApps` root in Kiro\. Generate a Power prompt:\n\n```bash\n"
    r"dw power prompt ua \\\n  --system rental-home \\\n"
    r"  --task \"Analyze the current architecture and refresh the project knowledge graph\"\n```",
)
text, count = kiro.subn(
    '''Open the `DW-SuperApps` root in Kiro and activate the native skill directly:

```text
/dw-ua Analyze the current architecture and refresh the project knowledge graph
```''',
    text,
)
if count != 1:
    raise SystemExit(f"expected one Kiro prompt example, found {count}")

codex = re.compile(
    r"Open the `DW-SuperApps` root in Codex\. Generate a Power prompt:\n\n```powershell\n"
    r"\.\\dw\.ps1 power prompt task-me `\n  --system rental-home `\n"
    r"  --task \"Create an implementation plan for OPS-LEASE\"\n```",
)
text, count = codex.subn(
    '''Open the `DW-SuperApps` root in Codex and activate the native skill directly:

```text
/dw-task-me Create an implementation plan for OPS-LEASE
```''',
    text,
)
if count != 1:
    raise SystemExit(f"expected one Codex prompt example, found {count}")
runtime.write_text(text, encoding="utf-8")

# Update checked-in adapters and indexes immediately; generator changes alone are
# insufficient because hosts read these files before the next adapter refresh.
direct_activation = '''## Activation

This Power is already active when this skill is selected or invoked through its native host alias.

Resolve one target system, load the canonical installed Power entrypoint, and apply it directly to the user's task in the current conversation.

Do not generate or execute a command to activate this Power.
Do not tell the user to run a slash command or terminal command.
Do not describe the Power instead of applying it.
'''
host_activation = '''## Power activation routing

When a registered Power skill or native alias is selected, load its canonical installed entrypoint and apply it directly to the user's request.

Do not generate a shell command, exported prompt, or copy-and-paste handoff to activate a Power.
'''
wrapper_pattern = re.compile(
    r"Generate a complete task prompt with:\n\n`dw power prompt [^`]+`\n"
)
host_pattern = re.compile(
    r"Generate a host-neutral prompt:\n\n`dw power prompt [^`]+`\n"
)
adapter_files: list[Path] = []
for relative in (
    ".codex/skills",
    ".kiro/skills",
    ".claude/skills",
    ".github/skills",
    ".agents/skills",
    ".clinerules",
    ".kilo/rules",
):
    base = ROOT / relative
    if base.exists():
        adapter_files.extend(path for path in base.rglob("*") if path.is_file())
for relative in ("CLAUDE.md", ".github/copilot-instructions.md", ".agents/DW_AGENT.md"):
    candidate = ROOT / relative
    if candidate.is_file():
        adapter_files.append(candidate)
for candidate in adapter_files:
    try:
        original = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    updated = wrapper_pattern.sub(direct_activation, original)
    updated = host_pattern.sub(host_activation, updated)
    if updated != original:
        candidate.write_text(updated, encoding="utf-8")

# Final active-surface scan. Historical evidence, generated plans, and changelog
# records are intentionally outside this operational command removal.
forbidden = "dw power " + "prompt"
active_files: list[Path] = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "CLAUDE.md",
]
for relative in (
    "bin",
    "scripts",
    "docs",
    "prompts",
    ".codex/skills",
    ".kiro/skills",
    ".claude/skills",
    ".github/skills",
    ".agents/skills",
    ".clinerules",
    ".kilo/rules",
):
    base = ROOT / relative
    if base.exists():
        active_files.extend(path for path in base.rglob("*") if path.is_file())
for relative in (".github/copilot-instructions.md", ".agents/DW_AGENT.md"):
    candidate = ROOT / relative
    if candidate.is_file():
        active_files.append(candidate)
violations: list[str] = []
for candidate in active_files:
    try:
        content = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if forbidden in content:
        violations.append(str(candidate.relative_to(ROOT)))
if violations:
    raise SystemExit("active references remain: " + ", ".join(sorted(set(violations))))

# Remove every temporary bootstrap and diagnostic artifact from the final diff.
for candidate in (ROOT / ".github/workflows").glob("remove-power-prompt*.yml"):
    candidate.unlink(missing_ok=True)
for candidate in (ROOT / "scripts").glob("remove_power_prompt_once*.py"):
    candidate.unlink(missing_ok=True)
shutil.rmtree(ROOT / ".diagnostics", ignore_errors=True)
