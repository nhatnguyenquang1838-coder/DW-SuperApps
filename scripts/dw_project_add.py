#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import dw_project_registry as registry

ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw project add")
    result.add_argument("project_id")
    result.add_argument("--repo", dest="repository", required=True)
    result.add_argument("--path")
    result.add_argument("--role", action="append", choices=sorted(registry.PROJECT_ROLES))
    result.add_argument("--system", action="store_true")
    result.add_argument("--system-id")
    result.add_argument("--enable-powers", default="")
    result.add_argument(
        "--offline",
        action="store_true",
        help="register an existing local project without git/submodule or network access",
    )
    return result


def preflight(args: argparse.Namespace) -> None:
    offline = bool(getattr(args, "offline", False))
    data = registry.workspace(ROOT)
    projects = registry.validate_registry(data, root=ROOT)
    if not registry.PROJECT_ID.fullmatch(args.project_id):
        raise registry.ProjectRegistryError(f"invalid project id: {args.project_id!r}")
    if args.project_id in projects:
        raise registry.ProjectRegistryError(f"project already exists: {args.project_id}")

    relative = registry.safe_relative_path(
        ROOT, args.path or f"projects/{args.project_id}"
    ).as_posix()
    registered_paths = {str(project["path"]) for project in projects.values()}
    if relative in registered_paths:
        raise registry.ProjectRegistryError(f"project path already registered: {relative}")
    if offline:
        if not (ROOT / relative).is_dir():
            raise registry.ProjectRegistryError(
                f"offline project path must already exist as a directory: {relative}"
            )
    elif (ROOT / relative).exists():
        raise registry.ProjectRegistryError(f"project path already exists: {relative}")

    source = registry.normalize_repo(args.repository)
    if not registry.REPOSITORY.fullmatch(source):
        raise registry.ProjectRegistryError("repository must use owner/name")

    roles = list(dict.fromkeys(args.role or ["product"]))
    if args.system and not ({"product", "system"} & set(roles)):
        raise registry.ProjectRegistryError(
            "a registered system requires product or system role"
        )
    if not args.system and (args.system_id or args.enable_powers):
        raise registry.ProjectRegistryError(
            "--system-id and --enable-powers require --system"
        )
    if offline and not args.system:
        raise registry.ProjectRegistryError("--offline requires --system for binding registration")

    system_id = args.system_id or args.project_id
    if args.system and not registry.PROJECT_ID.fullmatch(system_id):
        raise registry.ProjectRegistryError(f"invalid system id: {system_id!r}")
    existing_system_ids = {
        str(item.get("id"))
        for item in data.get("systems") or []
        if isinstance(item, dict)
    }
    if args.system and system_id in existing_system_ids:
        raise registry.ProjectRegistryError(f"system already exists: {system_id}")

    enabled = {
        item.strip()
        for item in (args.enable_powers or "").split(",")
        if item.strip()
    }
    known = {path.stem for path in (ROOT / "manifests" / "powers").glob("*.yaml")}
    unknown = enabled - known
    if unknown:
        raise registry.ProjectRegistryError(f"unknown enabled Powers: {sorted(unknown)}")


def main() -> int:
    try:
        args = parser().parse_args()
        preflight(args)
        return int(registry.project_add(args))
    except (registry.ProjectRegistryError, OSError, ValueError, KeyError) as exc:
        print(f"dw-project: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
