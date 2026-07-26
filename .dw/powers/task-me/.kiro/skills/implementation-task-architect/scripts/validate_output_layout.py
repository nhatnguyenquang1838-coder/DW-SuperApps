#!/usr/bin/env python3
"""Validate a generated run: exactly one complete folder per task."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_folder", help="Generated run folder under output.root")
    args = parser.parse_args()

    repo = Path.cwd().resolve()
    config = load_json(repo / ".task-architect" / "config.json")
    output_root = (repo / config["output"]["root"]).resolve()
    run_folder = Path(args.run_folder)
    if not run_folder.is_absolute():
        run_folder = (repo / run_folder).resolve()

    try:
        run_folder.relative_to(output_root)
    except ValueError:
        print("ERROR: run folder must be inside output.root")
        return 2

    task_files = set(config["output"]["task_files"].values())
    tasks_root = run_folder / "tasks"
    if not tasks_root.is_dir():
        print(f"ERROR: missing tasks directory: {tasks_root}")
        return 2

    folders = sorted(p for p in tasks_root.iterdir() if p.is_dir())
    if not folders:
        print("ERROR: no task folders found")
        return 2

    task_ids: set[str] = set()
    failures = 0
    for folder in folders:
        missing = sorted(name for name in task_files if not (folder / name).is_file())
        if missing:
            failures += 1
            print(f"ERROR: {folder.name} missing: {', '.join(missing)}")
            continue

        canonical = folder / config["output"]["task_files"]["canonical_task"]
        text = canonical.read_text(encoding="utf-8", errors="replace")
        task_id = None
        for line in text.splitlines():
            if line.startswith("task_id:"):
                task_id = line.split(":", 1)[1].strip().strip('"\'')
                break
        if not task_id:
            failures += 1
            print(f"ERROR: {canonical} has no top-level task_id")
        elif task_id in task_ids:
            failures += 1
            print(f"ERROR: duplicate task_id: {task_id}")
        else:
            task_ids.add(task_id)
            print(f"TASK_FOLDER_VALID {task_id} {folder}")

    if failures:
        print(f"OUTPUT_LAYOUT_INVALID failures={failures}")
        return 2

    print(f"OUTPUT_LAYOUT_VALID task_folders={len(folders)} task_ids={len(task_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
