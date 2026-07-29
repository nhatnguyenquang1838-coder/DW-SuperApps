#!/usr/bin/env python3
"""Read-only, source-owned help for the Task Me Power."""
from __future__ import annotations

import argparse
import json


HELP = {
    "id": "task-me",
    "name": "Task Me",
    "what": "Evidence-backed implementation planning for impact analysis, task decomposition, dependencies, estimates, and validation.",
    "when": [
        "Requirements, designs, architecture, or a UA graph exist and a change must be planned.",
        "You need to understand affected code, tests, contracts, data, or operational surfaces.",
        "An implementation agent needs self-contained tasks and a validation plan.",
    ],
    "how": [
        "Activate implementation-task-architect in the configured host.",
        "Configure .task-architect/config.json or the declared host config before planning.",
        "Use task-me-host.py validate --host-root <project> to verify external host boundaries.",
    ],
    "why": "Task Me exposes hidden impact and dependencies before coding while keeping planning separate from source mutation and delivery actions.",
    "gives": ["Requirement-to-code and requirement-to-test trace candidates", "Ordered tasks, dependency DAG, risk, complexity, and estimates", "Self-contained task folders with validation commands"],
    "doesNot": ["Edit application source, tests, requirements, or design files", "Create branches, commits, pull requests, or external task records"],
    "offline": "This command reads no project files and performs no network or runtime mutation.",
    "exitCodes": {"0": "Help rendered", "2": "Invalid command-line arguments"},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show read-only Task Me Power guidance")
    parser.add_argument("--json", action="store_true", help="emit the stable help contract as JSON")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(HELP, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    print("Task Me (task-me)")
    for key in ("what", "when", "how", "why", "gives", "doesNot"):
        value = HELP[key]
        label = {"doesNot": "Does not", "gives": "User gets"}.get(key, key.capitalize())
        print(f"{label}:")
        for item in value if isinstance(value, list) else [value]:
            print(f"  - {item}")
    print(f"Offline: {HELP['offline']}")
    print("Exit codes:")
    for code, meaning in HELP["exitCodes"].items():
        print(f"  {code}: {meaning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
