#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_required(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match for {label}, found {count}")
    return text.replace(old, new)


def remove_function(text: str, function_name: str, next_function: str, label: str) -> str:
    start_token = f"\n\ndef {function_name}("
    end_token = f"\n\ndef {next_function}("
    start = text.find(start_token)
    end = text.find(end_token, start + len(start_token))
    if start < 0 or end < 0:
        raise SystemExit(f"cannot locate {label}")
    return text[:start] + text[end:]


def main() -> None:
    # Remove shell dispatch for the obsolete prompt-export subcommand.
    path = "bin/dw"
    text = read(path)
    text = replace_required(
        text,
        '''    prompt)
      # shellcheck source=../scripts/python-resolver.sh
      source "$ROOT/scripts/python-resolver.sh"
      dw_exec_python "$ROOT/scripts/dw_workspace_dist.py" "$@"
      exit $?
      ;;
''',
        "",
        "bin/dw prompt route",
    )
    write(path, text)

    direct_activation = '''## Activation

This Power is already active when this skill is selected or invoked through its native host alias.

1. Resolve one target system from `workspace.yaml`.
2. Read the resolved canonical installed Power entrypoint directly.
3. Apply that Power to the user's task in the current conversation.
4. Continue until the task reaches a real capability, evidence, or authority boundary.

Do not generate or execute a command to activate this Power.
Do not tell the user to run a slash command or terminal command.
Do not describe the Power instead of applying it.
'''

    host_activation = '''## Power activation routing

When a registered Power skill or native alias is selected, load its canonical installed entrypoint and apply it directly to the user's request.

Do not generate a shell command, exported prompt, or copy-and-paste handoff to activate a Power.
'''

    old_wrapper = r'''## Invocation

1. Read `workspace.yaml` and `AGENTS.md` from DW-SuperApps.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Prefer the installed package entrypoint above; use source fallback only when no managed package exists.
5. Keep runtime and project configuration under the target system's `{spec['runtimeDataRoot']}/`.
6. Never create `.dw/powers`, host skill payloads, or distribution history inside the target system.

Generate a complete task prompt with:

`dw power prompt {power_id} --system <system> --task \"<task>\"`
'''

    old_host = r'''## Routing

1. Resolve the target system from `workspace.yaml`.
2. Load Power code from the workspace distribution store first.
3. Use source submodules only as an explicit compatibility fallback.
4. Keep runtime and project configuration inside the selected system repository.
5. Keep packages, inbox, history, bindings, router, and all host adapters in DW-SuperApps.
6. Never install Power skill payloads into a registered system.

Generate a host-neutral prompt:

`dw power prompt <power> --system <system> --task \"<task>\"`
'''

    new_host = '''## Routing

1. Resolve the target system from `workspace.yaml`.
2. Load Power code from the workspace distribution store first.
3. Use source submodules only as an explicit compatibility fallback.
4. Keep runtime and project configuration inside the selected system repository.
5. Keep packages, inbox, history, bindings, router, and all host adapters in DW-SuperApps.
6. Never install Power skill payloads into a registered system.

''' + host_activation

    # Remove the canonical CLI subcommand and generator instructions.
    path = "scripts/dw_cli.py"
    text = read(path)
    text = remove_function(text, "power_prompt", "submodule_entries", "dw_cli.power_prompt")
    text = replace_required(
        text,
        '''    power_prompt_parser = power_commands.add_parser("prompt")
    power_prompt_parser.add_argument("power_id")
    power_prompt_parser.add_argument("--system", dest="system_id", required=True)
    power_prompt_parser.add_argument("--task", default="")
    power_prompt_parser.set_defaults(handler=power_prompt)

''',
        "",
        "dw_cli prompt parser",
    )
    text = replace_required(text, old_wrapper, direct_activation, "dw_cli wrapper guidance")
    text = replace_required(text, old_host, new_host, "dw_cli host guidance")
    write(path, text)

    # Remove the compatibility CLI subcommand and generator instructions.
    path = "scripts/dw_workspace_dist.py"
    text = read(path)
    text = remove_function(text, "power_prompt", "parser", "dw_workspace_dist.power_prompt")
    text = replace_required(
        text,
        '''    power = commands.add_parser("power")
    power_commands = power.add_subparsers(dest="power_command", required=True)
    prompt = power_commands.add_parser("prompt")
    prompt.add_argument("power_id")
    prompt.add_argument("--system", dest="system_id", required=True)
    prompt.add_argument("--task", default="")
    prompt.set_defaults(handler=power_prompt)
''',
        "",
        "dw_workspace_dist prompt parser",
    )
    text = replace_required(text, old_wrapper, direct_activation, "dw_workspace_dist wrapper guidance")
    text = replace_required(text, old_host, new_host, "dw_workspace_dist host guidance")
    write(path, text)

    # Root routing contract: native skill activation only.
    path = "AGENTS.md"
    text = read(path)
    anchor = "## Mandatory runbooks\n"
    section = '''## Native Power activation

Power aliases such as `/dw-gwc`, `/dw-ua`, `/dw-task-me`, and `/dw-bmad` select native host skills. They are not terminal commands and do not require prompt export.

When a Power is selected, the agent must resolve the target system, load the canonical installed entrypoint, and apply the skill directly to the remainder of the user's request. It must not tell the user to execute an activation command, generate a copy-and-paste prompt, or merely explain the Power instead of using it.

The DW CLI owns installation, configuration, inspection, validation, doctor, history, rollback, and uninstall operations. It does not generate task prompts.

'''
    if section not in text:
        text = replace_required(text, anchor, section + anchor, "AGENTS activation anchor")
    write(path, text)

    # Replace the main multi-host usage section.
    path = "docs/MULTI_HOST_SETUP.md"
    text = read(path)
    section_pattern = re.compile(
        r"## Call a Power\n\n```bash\n.*?\n```\n\nPrompt output displays:\n\n"
        r"- workspace root;\n- package store and installed package;\n"
        r"- resolved entrypoint and fallback mode;\n- target system path;\n"
        r"- runtime root;\n- legacy target-install probe\.\n",
        re.S,
    )
    replacement = '''## Activate a Power

Use the native skill alias in the configured host and put the task after it:

```text
/dw-gwc Review governance and evidence
/dw-ua Analyze architecture
/dw-task-me Create an implementation plan
/dw-bmad Refine the product specification
```

The selected adapter resolves the target system and canonical installed entrypoint directly. No terminal command or generated task prompt is required.
'''
    text, count = section_pattern.subn(replacement, text)
    if count != 1:
        raise SystemExit(f"expected one MULTI_HOST_SETUP section, found {count}")
    write(path, text)

    # Convert remaining active documentation examples. Preserve historical plans,
    # generated evidence, and changelog records.
    active_files = [ROOT / "README.md"]
    for base in (ROOT / "docs", ROOT / "prompts"):
        if base.exists():
            active_files.extend(path for path in base.rglob("*") if path.is_file())

    command_pattern = re.compile(
        r'dw power prompt ([a-z0-9-]+) --system [^\s`]+ --task "([^"]*)"'
    )
    placeholder_pattern = re.compile(
        r'dw power prompt <power> --system <system> --task ["\\]*<task>["\\]*'
    )
    for doc in active_files:
        try:
            original = doc.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = command_pattern.sub(lambda match: f"/dw-{match.group(1)} {match.group(2)}", original)
        updated = placeholder_pattern.sub("/dw-<power> <task>", updated)
        updated = updated.replace(
            "Generate a host-neutral prompt:",
            "Activate the selected native Power skill:",
        )
        updated = updated.replace(
            "Generate a complete task prompt with:",
            "Apply the selected native Power directly:",
        )
        if updated != original:
            doc.write_text(updated, encoding="utf-8")

    # Regression coverage.
    (ROOT / "tests/test_power_prompt_removed.py").write_text(
        '''from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "dw power " + "prompt"


class PowerPromptRemovalTests(unittest.TestCase):
    def test_command_is_not_registered(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/dw_cli.py"),
                "power",
                "prompt",
                "gwc",
                "--system",
                "rental-home",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Use the `gwc` Power", result.stdout)

    def test_active_generators_do_not_emit_prompt_export(self) -> None:
        for relative in ("scripts/dw_cli.py", "scripts/dw_workspace_dist.py", "bin/dw"):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(FORBIDDEN, content, relative)
            self.assertNotIn("Generate a complete task prompt", content, relative)
            self.assertNotIn("Generate a host-neutral prompt", content, relative)

    def test_root_contract_requires_direct_activation(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Native Power activation", content)
        self.assertIn("does not generate task prompts", content)


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )

    # No active source or documentation may retain the removed command.
    forbidden = "dw power " + "prompt"
    checks = [
        ROOT / "bin/dw",
        ROOT / "scripts/dw_cli.py",
        ROOT / "scripts/dw_workspace_dist.py",
        ROOT / "AGENTS.md",
        ROOT / "README.md",
    ]
    checks.extend(
        path
        for base in (ROOT / "docs", ROOT / "prompts")
        if base.exists()
        for path in base.rglob("*")
        if path.is_file()
    )
    violations: list[str] = []
    for candidate in checks:
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if forbidden in content:
            violations.append(str(candidate.relative_to(ROOT)))
    if violations:
        raise SystemExit("active references remain: " + ", ".join(sorted(set(violations))))

    # Remove all one-shot implementation files from the final branch diff.
    for relative in (
        ".github/workflows/remove-power-prompt-once.yml",
        ".github/workflows/remove-power-prompt-pr.yml",
        "scripts/remove_power_prompt_once.py",
    ):
        (ROOT / relative).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
