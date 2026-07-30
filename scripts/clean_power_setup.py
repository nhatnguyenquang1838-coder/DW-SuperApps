#!/usr/bin/env python3
"""Return a DW-SuperApps checkout to its pre-Power package setup state."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    from dw_project_targets import ProjectTargetError, project_path, runtime_projects
except ModuleNotFoundError:
    from scripts.dw_project_targets import ProjectTargetError, project_path, runtime_projects

try:
    import yaml
except ImportError as exc:  # pragma: no cover - handled by the workspace launcher
    print("Missing PyYAML. Run: python -m pip install -r requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2) from exc

ROOT = Path(__file__).resolve().parents[1]
CONFIGURED_ROOTS = (
    ("store", "storeRoot", ".dw/powers"),
    ("inbox", "inboxRoot", ".dw/inbox/powers"),
    ("cache", "cacheRoot", ".dw/cache"),
    ("history", "historyRoot", ".dw/history/powers"),
    ("bindings", "bindingsRoot", ".dw/bindings"),
)


class CleanupError(RuntimeError):
    pass


def load_workspace(root: Path = ROOT) -> dict[str, Any]:
    path = root / "workspace.yaml"
    if not path.is_file():
        raise CleanupError(f"missing workspace manifest: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CleanupError(f"workspace manifest must be a mapping: {path}")
    return data


def resolve_owned_root(root: Path, value: str, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        raise CleanupError(f"refusing external {label} root: {value}")
    candidate = root / raw
    if candidate.is_symlink():
        raise CleanupError(f"refusing symlink {label} root: {candidate}")
    resolved = candidate.resolve()
    dw_root = (root / ".dw").resolve()
    try:
        resolved.relative_to(dw_root)
    except ValueError as exc:
        raise CleanupError(f"{label} root must remain under .dw: {value}") from exc
    if resolved == dw_root:
        raise CleanupError(f"refusing to remove the entire .dw directory for {label}")
    return resolved


def distribution_paths(root: Path = ROOT) -> list[tuple[str, Path]]:
    data = load_workspace(root)
    distribution = data.get("distribution") or {}
    if not isinstance(distribution, dict):
        raise CleanupError("workspace distribution must be a mapping")
    paths: list[tuple[str, Path]] = []
    for label, key, fallback in CONFIGURED_ROOTS:
        value = distribution.get(key, fallback)
        if not isinstance(value, str) or not value.strip():
            raise CleanupError(f"workspace distribution.{key} must be a path string")
        paths.append((label, resolve_owned_root(root, value, label=label)))
    paths.extend(
        [
            ("distributions", resolve_owned_root(root, ".dw/distributions", label="build")),
            (
                "offline-history",
                resolve_owned_root(root, ".dw/history/offline-releases", label="offline history"),
            ),
        ]
    )
    unique: dict[Path, str] = {}
    for label, path in paths:
        previous = unique.get(path)
        if previous:
            raise CleanupError(f"distribution roots overlap: {previous} and {label}")
        for other, other_label in unique.items():
            try:
                path.relative_to(other)
                nested = True
            except ValueError:
                try:
                    other.relative_to(path)
                    nested = True
                except ValueError:
                    nested = False
            if nested:
                raise CleanupError(f"distribution roots overlap: {other_label} and {label}")
        unique[path] = label
    return paths


def runtime_paths(data: dict[str, Any], root: Path = ROOT) -> list[tuple[str, Path]]:
    ownership = data.get("data_ownership") or {}
    declared = ownership.get("roots") if isinstance(ownership, dict) else None
    if not isinstance(declared, dict):
        return []
    paths: list[tuple[str, Path]] = []
    for project in runtime_projects(data):
        project_id = str(project.get("id", "unknown"))
        try:
            system_candidate = project_path(project, root)
        except ProjectTargetError as exc:
            raise CleanupError(str(exc)) from exc
        if system_candidate.is_symlink():
            raise CleanupError(f"refusing symlink project path: {system_candidate}")
        system_path = system_candidate.resolve()
        try:
            system_path.relative_to(root.resolve())
        except ValueError as exc:
            raise CleanupError(f"project path escapes workspace: {system_path}") from exc
        for name, relative in declared.items():
            if not isinstance(relative, str) or not relative.strip():
                raise CleanupError(f"runtime root {name} must be a path string")
            runtime_candidate = system_path / relative
            runtime = runtime_candidate.resolve()
            try:
                runtime.relative_to(system_path)
            except ValueError as exc:
                raise CleanupError(f"runtime root escapes project {project_id}: {relative}") from exc
            paths.append((f"runtime:{project_id}:{name}", runtime_candidate))
    return paths


def generated_adapter_paths(root: Path = ROOT) -> list[Path]:
    import dw_workspace_dist

    original_root = dw_workspace_dist.ROOT
    original_workspace_path = dw_workspace_dist.WORKSPACE_PATH
    original_manifest_dir = dw_workspace_dist.MANIFEST_DIR
    dw_workspace_dist.ROOT = root
    dw_workspace_dist.WORKSPACE_PATH = root / "workspace.yaml"
    dw_workspace_dist.MANIFEST_DIR = root / "manifests" / "powers"
    try:
        host_expected_paths = dw_workspace_dist.expected_host_paths
        is_generated_path = dw_workspace_dist.is_generated_path
        select_hosts = dw_workspace_dist.select_hosts

        paths: list[Path] = []
        for host in select_hosts("all"):
            for path in host_expected_paths(host):
                target = path.parent if path.name == "SKILL.md" else path
                if (target.exists() or target.is_symlink()) and is_generated_path(target):
                    paths.append(target)
        return sorted(set(paths))
    finally:
        dw_workspace_dist.ROOT = original_root
        dw_workspace_dist.WORKSPACE_PATH = original_workspace_path
        dw_workspace_dist.MANIFEST_DIR = original_manifest_dir


def build_plan(*, include_runtime: bool, root: Path = ROOT) -> dict[str, list[str]]:
    data = load_workspace(root)
    remove: list[str] = []
    for _label, path in distribution_paths(root):
        if path.exists() or path.is_symlink():
            remove.append(str(path))
    remove.extend(str(path) for path in generated_adapter_paths(root))
    if include_runtime:
        remove.extend(str(path) for _label, path in runtime_paths(data, root))
    return {
        "remove": sorted(dict.fromkeys(remove)),
        "preserve": [
            str(root / "workspace.yaml"),
            "registered projects",
            "Power source submodules",
            "runtime roots unless --include-runtime is supplied",
            "legacy target .dw installations",
        ],
    }


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def cleanup(*, yes: bool, include_runtime: bool, root: Path = ROOT) -> dict[str, Any]:
    if include_runtime and not yes:
        raise CleanupError("--include-runtime requires --yes")
    plan = build_plan(include_runtime=include_runtime, root=root)
    if not yes:
        return {"status": "DRY_RUN", **plan}
    removed: list[str] = []
    for raw in plan["remove"]:
        path = Path(raw)
        if path.exists() or path.is_symlink():
            remove_path(path)
            removed.append(raw)
    return {"status": "CLEANED", "removed": removed, "preserve": plan["preserve"]}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="dw power cleanup",
        description="Remove workspace Power setup while preserving project runtime by default",
    )
    result.add_argument("command", nargs="?", choices=["cleanup"], default="cleanup")
    result.add_argument("--include-runtime", action="store_true")
    result.add_argument("--yes", action="store_true", help="apply the destructive cleanup")
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        print(json.dumps(cleanup(yes=args.yes, include_runtime=args.include_runtime), indent=2))
        return 0
    except (CleanupError, OSError, ValueError, KeyError) as exc:
        print(f"dw-power-cleanup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
