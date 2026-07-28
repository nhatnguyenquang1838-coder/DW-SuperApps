#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:
    print("Missing PyYAML. Run: python -m pip install -r requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2) from exc

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PATH = ROOT / "workspace.yaml"
PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
PROJECT_ROLES = {"power-source", "product", "system", "library", "tooling"}
RUNTIME_FILES = (
    "AGENTS.md",
    "requirements-dev.txt",
    "dw.ps1",
    "dw.cmd",
)
RUNTIME_DIRS = (
    "bin",
    "scripts",
    "schemas",
    "manifests",
    "prompts",
    "docs/runbooks",
    "powers/bmad",
)
IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


class ProjectRegistryError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ProjectRegistryError(f"missing file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProjectRegistryError(f"expected YAML mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def workspace(root: Path = ROOT) -> dict[str, Any]:
    return load_yaml(root / "workspace.yaml")


def normalize_repo(value: str) -> str:
    result = value.strip()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    if result.endswith(".git"):
        result = result[:-4]
    return result.strip("/")


def safe_relative_path(root: Path, value: str, *, allow_root: bool = False) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        raise ProjectRegistryError(f"project path must be relative: {value}")
    resolved = (root / raw).resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ProjectRegistryError(f"project path escapes workspace: {value}") from exc
    if not allow_root and str(relative) in {"", "."}:
        raise ProjectRegistryError("project path cannot be the workspace root")
    return relative


def project_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("projects") or []
    if not isinstance(rows, list):
        raise ProjectRegistryError("workspace projects must be a list")
    if not all(isinstance(item, dict) for item in rows):
        raise ProjectRegistryError("workspace project entries must be mappings")
    return rows


def validate_registry(
    data: dict[str, Any],
    *,
    root: Path,
    gitmodules: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    projects: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for project in project_entries(data):
        project_id = project.get("id")
        if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
            raise ProjectRegistryError(f"invalid project id: {project_id!r}")
        if project_id in projects:
            raise ProjectRegistryError(f"duplicate project id: {project_id}")
        path = project.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ProjectRegistryError(f"project {project_id} requires path")
        relative = safe_relative_path(root, path).as_posix()
        if relative in paths:
            raise ProjectRegistryError(f"duplicate project path: {relative}")
        repository = project.get("source") or project.get("repository")
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(normalize_repo(repository)):
            raise ProjectRegistryError(f"project {project_id} requires owner/repository source")
        roles = project.get("roles") or []
        if not isinstance(roles, list) or not roles:
            raise ProjectRegistryError(f"project {project_id} requires at least one role")
        unknown_roles = set(map(str, roles)) - PROJECT_ROLES
        if unknown_roles:
            raise ProjectRegistryError(
                f"project {project_id} has unsupported roles: {sorted(unknown_roles)}"
            )
        if gitmodules is not None:
            if relative not in gitmodules:
                raise ProjectRegistryError(
                    f"project {project_id} path is not registered in .gitmodules: {relative}"
                )
            configured = normalize_repo(gitmodules[relative])
            if configured != normalize_repo(repository):
                raise ProjectRegistryError(
                    f"project {project_id} repository mismatch: workspace={normalize_repo(repository)} "
                    f"gitmodules={configured}"
                )
        normalized = dict(project)
        normalized["path"] = relative
        normalized["source"] = normalize_repo(repository)
        normalized["roles"] = list(map(str, roles))
        projects[project_id] = normalized
        paths.add(relative)

    for power in data.get("powers") or []:
        if not isinstance(power, dict):
            raise ProjectRegistryError("workspace power entries must be mappings")
        project_id = power.get("project")
        if project_id is not None:
            if project_id not in projects:
                raise ProjectRegistryError(
                    f"Power {power.get('id')} references unknown project: {project_id}"
                )
            project = projects[str(project_id)]
            if "power-source" not in project["roles"]:
                raise ProjectRegistryError(
                    f"Power {power.get('id')} project {project_id} lacks power-source role"
                )
            if power.get("path") and power["path"] != project["path"]:
                raise ProjectRegistryError(f"Power path mismatch for project {project_id}")
            if power.get("source") and normalize_repo(str(power["source"])) != project["source"]:
                raise ProjectRegistryError(f"Power source mismatch for project {project_id}")

    for system in data.get("systems") or []:
        if not isinstance(system, dict):
            raise ProjectRegistryError("workspace system entries must be mappings")
        project_id = system.get("project")
        if project_id is not None:
            if project_id not in projects:
                raise ProjectRegistryError(
                    f"system {system.get('id')} references unknown project: {project_id}"
                )
            project = projects[str(project_id)]
            if not ({"system", "product"} & set(project["roles"])):
                raise ProjectRegistryError(
                    f"system {system.get('id')} project {project_id} lacks system/product role"
                )
            if system.get("path") and system["path"] != project["path"]:
                raise ProjectRegistryError(f"system path mismatch for project {project_id}")
            if system.get("source") and normalize_repo(str(system["source"])) != project["source"]:
                raise ProjectRegistryError(f"system source mismatch for project {project_id}")
    return projects


def find_project(project_id: str, root: Path = ROOT) -> dict[str, Any]:
    projects = validate_registry(workspace(root), root=root)
    if project_id not in projects:
        raise ProjectRegistryError(f"unknown project: {project_id}")
    return projects[project_id]


def project_list(args: argparse.Namespace) -> int:
    projects = validate_registry(workspace(ROOT), root=ROOT)
    rows = list(projects.values())
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    print(f"{'ID':<18} {'ROLES':<28} {'PATH':<28} SOURCE")
    for row in rows:
        print(
            f"{row['id']:<18} {','.join(row['roles']):<28} "
            f"{row['path']:<28} {row['source']}"
        )
    return 0


def project_info(args: argparse.Namespace) -> int:
    project = find_project(args.project_id)
    if args.json:
        print(json.dumps(project, indent=2, ensure_ascii=False))
        return 0
    print(f"Project: {project['id']}")
    print(f"Path: {project['path']}")
    print(f"Source: {project['source']}")
    print(f"Roles: {', '.join(project['roles'])}")
    return 0


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_NAMES or name.endswith((".pyc", ".pyo"))}


def copy_runtime(source_root: Path, target: Path) -> list[str]:
    created: list[str] = []
    for relative in RUNTIME_FILES:
        source = source_root / relative
        if not source.is_file():
            continue
        destination = target / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        created.append(relative)
    for relative in RUNTIME_DIRS:
        source = source_root / relative
        if not source.exists():
            continue
        destination = target / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, ignore=ignored)
        else:
            shutil.copy2(source, destination)
        created.append(relative)
    return created


def template_workspace(workspace_id: str, name: str) -> dict[str, Any]:
    return {
        "apiVersion": "ai-workspace/v1",
        "kind": "Workspace",
        "metadata": {"id": workspace_id, "name": name},
        "hosts": ["kiro", "codex", "copilot", "cline", "kilo", "claude", "custom"],
        "providers": [
            {
                "id": "ollama",
                "type": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "api_key": "ollama",
                "model_env": "OLLAMA_MODEL",
            }
        ],
        "distribution": {
            "ownership": "workspace",
            "storeRoot": ".dw/powers",
            "inboxRoot": ".dw/inbox/powers",
            "cacheRoot": ".dw/cache",
            "historyRoot": ".dw/history/powers",
            "bindingsRoot": ".dw/bindings",
            "hostAdaptersRoot": ".",
        },
        "projects": [],
        "powers": [],
        "systems": [],
        "data_ownership": {
            "policy": "system-owned",
            "roots": {"ua": ".ua", "task_me": ".task-me", "gwc": ".gwc", "bmad": ".bmad"},
        },
    }


def ensure_git_repository(target: Path) -> None:
    if (target / ".git").exists():
        return
    result = subprocess.run(["git", "init"], cwd=target, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ProjectRegistryError(result.stderr.strip() or "git init failed")


def workspace_init(args: argparse.Namespace) -> int:
    target = Path(args.target).expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise ProjectRegistryError(f"target is not a directory: {target}")
    target.mkdir(parents=True, exist_ok=True)
    existing = [item.name for item in target.iterdir() if item.name != ".git"]
    if existing and not args.in_place:
        raise ProjectRegistryError(
            "target is not empty; use --in-place for a non-destructive initialization"
        )
    workspace_path = target / "workspace.yaml"
    if workspace_path.exists():
        raise ProjectRegistryError(f"refusing to overwrite existing {workspace_path}")
    created = copy_runtime(ROOT, target)
    write_yaml(workspace_path, template_workspace(args.workspace_id, args.name))
    created.append("workspace.yaml")
    (target / "projects").mkdir(exist_ok=True)
    (target / ".dw" / "inbox" / "powers").mkdir(parents=True, exist_ok=True)
    ensure_git_repository(target)
    print(f"INITIALIZED: {target}")
    print(f"Workspace: {args.name} ({args.workspace_id})")
    print(f"Created runtime entries: {len(created)}")
    print("Next:")
    print(f"  cd {target}")
    print("  ./bin/dw install --shell auto")
    print("  ./bin/dw project list")
    print("  ./bin/dw validate")
    return 0


def git(*args: str, cwd: Path = ROOT) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ProjectRegistryError(result.stderr.strip() or f"git {' '.join(args)} failed")


def project_add(args: argparse.Namespace) -> int:
    data = workspace(ROOT)
    projects = validate_registry(data, root=ROOT)
    if args.project_id in projects:
        raise ProjectRegistryError(f"project already exists: {args.project_id}")
    relative = safe_relative_path(ROOT, args.path or f"projects/{args.project_id}").as_posix()
    source = normalize_repo(args.repository)
    if not REPOSITORY.fullmatch(source):
        raise ProjectRegistryError("repository must use owner/name")
    if (ROOT / relative).exists():
        raise ProjectRegistryError(f"project path already exists: {relative}")
    git("submodule", "add", f"https://github.com/{source}.git", relative)
    roles = list(dict.fromkeys(args.role or ["product"]))
    data.setdefault("projects", []).append(
        {"id": args.project_id, "path": relative, "source": source, "roles": roles}
    )
    if args.system:
        enabled = [item for item in (args.enable_powers or "").split(",") if item]
        data.setdefault("systems", []).append(
            {
                "id": args.system_id or args.project_id,
                "project": args.project_id,
                "path": relative,
                "source": source,
                "enabled_powers": enabled,
            }
        )
    write_yaml(WORKSPACE_PATH, data)
    print(f"ADDED: {args.project_id} -> {relative}")
    print("Review: git diff -- .gitmodules workspace.yaml")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw", description="DW project registry and Super Project bootstrap")
    commands = result.add_subparsers(dest="command", required=True)

    workspace_parser = commands.add_parser("workspace")
    workspace_commands = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    init = workspace_commands.add_parser("init")
    init.add_argument("target", nargs="?", default=".")
    init.add_argument("--id", dest="workspace_id", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--in-place", action="store_true")
    init.set_defaults(handler=workspace_init)

    project_parser = commands.add_parser("project")
    project_commands = project_parser.add_subparsers(dest="project_command", required=True)
    list_command = project_commands.add_parser("list")
    list_command.add_argument("--json", action="store_true")
    list_command.set_defaults(handler=project_list)
    info = project_commands.add_parser("info")
    info.add_argument("project_id")
    info.add_argument("--json", action="store_true")
    info.set_defaults(handler=project_info)
    add = project_commands.add_parser("add")
    add.add_argument("project_id")
    add.add_argument("--repo", dest="repository", required=True)
    add.add_argument("--path")
    add.add_argument("--role", action="append", choices=sorted(PROJECT_ROLES))
    add.add_argument("--system", action="store_true")
    add.add_argument("--system-id")
    add.add_argument("--enable-powers", default="")
    add.set_defaults(handler=project_add)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = parser().parse_args(list(argv) if argv is not None else None)
        return int(args.handler(args))
    except (ProjectRegistryError, OSError, ValueError, KeyError) as exc:
        print(f"dw-project: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
