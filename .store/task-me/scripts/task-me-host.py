#!/usr/bin/env python3
"""Task Me host-mode boundary validator.

This script lets a Task Me distribution operate against an external host project
without assuming that the Task Me package directory is the product repository.
It performs read-only path resolution and reports the resolved execution roots.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


class HostModeError(ValueError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on runtime image
            raise HostModeError("YAML config requires PyYAML; use JSON or install PyYAML") from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise HostModeError("host config must be an object")
    return data


def resolve_under(root: Path, value: str, label: str) -> Path:
    if not value or "\x00" in value:
        raise HostModeError(f"{label} must be a non-empty path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise HostModeError(f"{label} escapes host root: {value}") from exc
    return resolved


def normalize_inputs(config: dict[str, Any]) -> dict[str, Any]:
    schema_version = config.get("schemaVersion") or config.get("schema_version")
    if schema_version not in {"1.0", "1"}:
        raise HostModeError("schemaVersion must be 1.0")
    folder_mode = config.get("folderMode") or config.get("folder_mode")
    if folder_mode != "per_task":
        raise HostModeError("folderMode must be per_task")
    output = config.get("output")
    if not isinstance(output, dict):
        raise HostModeError("output must be an object")
    task_files = output.get("taskFiles") or output.get("task_files")
    if not isinstance(task_files, list) or len(task_files) < 8:
        raise HostModeError("output.taskFiles must contain the complete task file set")
    return config


def validate_roots(args: argparse.Namespace) -> dict[str, str]:
    package_root = Path(args.package_root).resolve()
    host_root = Path(args.host_root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = host_root / config_path
    config_path = resolve_under(host_root, str(config_path), "config")
    config = normalize_inputs(load_config(config_path))

    ua_value = args.ua_root or config.get("knowledgeRoot") or config.get("knowledge", {}).get("root")
    output_value = args.output_root or config.get("outputRoot") or config.get("output", {}).get("root")
    runtime_value = config.get("runtimeRoot") or config.get("runtime", {}).get("root") or ".task-me"

    if ua_value != ".ua" and not str(ua_value).startswith(".ua/"):
        raise HostModeError("knowledge root must be .ua or a path below .ua")
    if runtime_value != ".task-me" and not str(runtime_value).startswith(".task-me/"):
        raise HostModeError("runtime root must be .task-me or a path below .task-me")

    ua_root = resolve_under(host_root, str(ua_value), "ua_root")
    output_root = resolve_under(host_root, str(output_value), "output_root")
    runtime_root = resolve_under(host_root, str(runtime_value), "runtime_root")

    if package_root == host_root:
        raise HostModeError("package_root and host_root must be separate in host mode")
    if output_root == host_root:
        raise HostModeError("output_root may not be the host root")

    return {
        "package_root": str(package_root),
        "host_root": str(host_root),
        "config": str(config_path),
        "ua_root": str(ua_root),
        "output_root": str(output_root),
        "runtime_root": str(runtime_root),
        "write_mode": "output_only",
        "folder_mode": "per_task",
    }


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        result = validate_roots(args)
    except Exception as exc:
        print(f"HOST_MODE_INVALID: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"status": "HOST_MODE_VALID", "roots": result}, indent=2, sort_keys=True))
    else:
        print("HOST_MODE_VALID")
        for key, value in result.items():
            print(f"{key}={value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Task Me host-mode roots")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate host-mode path boundaries")
    validate.add_argument("--package-root", default=os.getcwd(), help="Task Me package root")
    validate.add_argument("--host-root", required=True, help="external superproject root")
    validate.add_argument("--config", default=".task-me/task-architect.yaml", help="host-owned config path")
    validate.add_argument("--ua-root", default=None, help="override UA graph root")
    validate.add_argument("--output-root", default=None, help="override output root")
    validate.add_argument("--json", action="store_true", help="emit JSON")
    validate.set_defaults(func=cmd_validate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
