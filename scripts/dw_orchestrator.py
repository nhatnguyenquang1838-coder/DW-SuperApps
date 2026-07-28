#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PATH = ROOT / "workspace.yaml"
INTENTS_PATH = ROOT / "manifests" / "orchestration" / "intents.yaml"


class OrchestratorError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OrchestratorError(f"missing file: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError as exc:
        raise OrchestratorError("PyYAML is required") from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise OrchestratorError(f"expected YAML mapping: {path}")
    return data


def find_system(system_id: str) -> dict[str, Any]:
    workspace = load_yaml(WORKSPACE_PATH)
    for system in workspace.get("systems", []):
        if isinstance(system, dict) and system.get("id") == system_id:
            return system
    raise OrchestratorError(f"unknown system: {system_id}")


def load_intents() -> dict[str, Any]:
    if not INTENTS_PATH.is_file():
        return {"intents": {}}
    return load_yaml(INTENTS_PATH)


def resolve_workspace_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / value
    return path.resolve()


def exact_intent_matches(task_text: str, intent_ids: list[str]) -> list[str]:
    lowered = task_text.lower()
    matches: list[str] = []
    for intent_id in intent_ids:
        pattern = re.compile(rf"(?<!\w){re.escape(intent_id)}(?!\w)", re.IGNORECASE)
        if pattern.search(lowered):
            matches.append(intent_id)
    return matches


def orchestration_block(system: dict[str, Any]) -> dict[str, Any]:
    block = system.get("orchestration")
    if not isinstance(block, dict):
        raise OrchestratorError(f"system {system.get('id')} has no orchestration block")
    return block


def applicable_hooks(system: dict[str, Any], matched_intents: set[str]) -> list[dict[str, Any]]:
    block = orchestration_block(system)
    hooks = block.get("hooks", [])
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for hook in hooks:
        gate = str(hook.get("gate", ""))
        worker = str(hook.get("worker", ""))
        intents = [str(i) for i in hook.get("intents", [])]
        output_into = str(hook.get("output_into", ""))
        key = (gate, worker, output_into)
        if key in seen:
            continue
        seen.add(key)
        if matched_intents.intersection(set(intents)):
            results.append(
                {
                    "gate": gate,
                    "worker": worker,
                    "intents": sorted(matched_intents.intersection(set(intents))),
                    "output_into": output_into,
                }
            )
    return results


def build_primary_prompt(system: dict[str, Any], task: str) -> str:
    system_id = system.get("id", "unknown")
    system_path = resolve_workspace_path(system["path"])
    block = orchestration_block(system)
    primary = block.get("primary", "gwc")
    workers = ", ".join(block.get("workers", [])) or "none"
    hooks = applicable_hooks(system, set())
    lines = [
        f"Use the `{primary}` Power as the primary governance workflow for system `{system_id}`.",
        "",
        f"Task: {task}",
        "",
        "Registered worker powers for delegation:",
    ]
    for hook in hooks:
        lines.append(
            f"- Gate `{hook['gate']}` → `{hook['worker']}` for intents {', '.join(hook['intents'])}; feed into `{hook['output_into']}`"
        )
    lines.extend(
        [
            "",
            "When this task matches one of the worker intents above, invoke the worker via:",
            f"`dw orchestrator run --system {system_id} --task \"{task}\"`",
            "",
            "Keep generated runtime and configuration inside the system repository. Do not create Power skill payloads inside the system.",
        ]
    )
    return os.linesep.join(lines)


def build_worker_prompts(system: dict[str, Any], task: str, matched_intents: set[str]) -> list[dict[str, Any]]:
    hooks = applicable_hooks(system, matched_intents)
    prompts: list[dict[str, Any]] = []
    for hook in hooks:
        prompts.append(
            {
                "gate": hook["gate"],
                "worker": hook["worker"],
                "task": task,
                "intents": hook["intents"],
                "output_into": hook["output_into"],
                "prompt": f"Use the `{hook['worker']}` Power for system `{system.get('id')}`.",
            }
        )
    return prompts


def cmd_prompt(args: argparse.Namespace) -> int:
    system = find_system(args.system_id)
    task = args.task.strip() or "<describe the task>"
    intents_registry = load_intents()
    all_intents = sorted(intents_registry.get("intents", {}).keys())
    matched = set(exact_intent_matches(task, all_intents))
    if matched:
        selected = sorted(matched)
        note = "Exact intent matches: " + ", ".join(selected)
    else:
        selected = []
        note = "No exact intent match; worker delegation requires host LLM judgment from candidates."
    print(build_primary_prompt(system, task))
    print()
    print("## Orchestration notes")
    print(note)
    if selected:
        print("Matched intents: " + ", ".join(selected))
    else:
        block = orchestration_block(system)
        hooks = block.get("hooks", [])
        candidate_intents = []
        for hook in hooks:
            candidate_intents.extend([str(i) for i in hook.get("intents", [])])
        unique_candidates = sorted(set(candidate_intents))
        print("Candidate intents for host judgment: " + ", ".join(unique_candidates))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    system = find_system(args.system_id)
    task = args.task.strip() or "<describe the task>"
    intents_registry = load_intents()
    all_intents = sorted(intents_registry.get("intents", {}).keys())
    matched = set(exact_intent_matches(task, all_intents))
    if not matched:
        block = orchestration_block(system)
        hooks = block.get("hooks", [])
        candidate_intents = []
        for hook in hooks:
            candidate_intents.extend([str(i) for i in hook.get("intents", [])])
        matched = set(candidate_intents)
    worker_prompts = build_worker_prompts(system, task, matched)
    phases: list[dict[str, Any]] = [
        {
            "phase": 1,
            "power": orchestration_block(system).get("primary", "gwc"),
            "task": task,
            "role": "primary",
            "feeds_into": [],
        }
    ]
    for idx, prompt in enumerate(worker_prompts, start=2):
        phases.append(
            {
                "phase": idx,
                "power": prompt["worker"],
                "task": prompt["task"],
                "role": "worker",
                "gate": prompt["gate"],
                "intents": prompt["intents"],
                "output_into": prompt["output_into"],
                "feeds_into": [prompt["output_into"]],
            }
        )
    result = {
        "system_id": system.get("id"),
        "task": task,
        "matched_intents": sorted(matched),
        "phases": phases,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw orchestrator", description="DW SuperApps orchestration")
    commands = result.add_subparsers(dest="command", required=True)

    prompt_parser = commands.add_parser("prompt")
    prompt_parser.add_argument("--system", dest="system_id", required=True)
    prompt_parser.add_argument("--task", default="")
    prompt_parser.set_defaults(handler=cmd_prompt)

    run_parser = commands.add_parser("run")
    run_parser.add_argument("--system", dest="system_id", required=True)
    run_parser.add_argument("--task", default="")
    run_parser.set_defaults(handler=cmd_run)

    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(args.handler(args))
    except (OrchestratorError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"dw-orchestrator: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
