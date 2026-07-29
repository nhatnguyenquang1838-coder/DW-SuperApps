#!/usr/bin/env python3
"""Read-only, source-owned help for the Understand Anything Power."""
from __future__ import annotations

import argparse
import json


HELP = {
    "id": "ua",
    "name": "Understand Anything",
    "what": "Semantic codebase analysis that produces a project knowledge graph for architecture, components, and dependencies.",
    "when": [
        "You are onboarding to an unfamiliar, stale, or structurally complex repository.",
        "You need architecture discovery, dependency mapping, or impact evidence before planning.",
        "The project changed substantially and its canonical knowledge graph needs a refresh.",
    ],
    "how": [
        "Invoke the understand skill with an optional project path.",
        "Use --full for a rebuild, --review for graph review, and --exclude for additional patterns.",
        "Use --language <lang> to select output language and --auto-update or --no-auto-update for commit updates.",
    ],
    "options": ["[path]", "--full", "--auto-update", "--no-auto-update", "--review", "--language <lang>", "--exclude <patterns>"],
    "why": "UA gives planning and implementation work a repository-grounded map instead of relying on guesses or incomplete browsing.",
    "gives": ["A canonical knowledge graph under the consumer .ua runtime", "Architecture and dependency evidence", "Incremental or full analysis guidance"],
    "doesNot": ["Modify application source code during normal analysis", "Create tasks, branches, pull requests, or external work items"],
    "offline": "This command only renders bundled help. The help path does not scan a project, write .ua files, or contact a remote service.",
    "exitCodes": {"0": "Help rendered", "2": "Invalid command-line arguments"},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show read-only Understand Anything Power guidance")
    parser.add_argument("--json", action="store_true", help="emit the stable help contract as JSON")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(HELP, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    print("Understand Anything (ua)")
    for key in ("what", "when", "how", "options", "why", "gives", "doesNot"):
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
