#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import dw_project_registry as registry

registry.RUNTIME_FILES = tuple(
    dict.fromkeys(
        [
            *registry.RUNTIME_FILES,
            "README.md",
            "docs/POWER_CONSUMER_RUNTIME_V1.md",
            "docs/POWER_RUNTIME_V2.md",
            "docs/PORTABLE_MULTI_HOST_ROUTER.md",
            "docs/MULTI_HOST_SETUP.md",
            "docs/DW_SUPER_SETUP.md",
        ]
    )
)
registry.RUNTIME_DIRS = tuple(
    dict.fromkeys([*registry.RUNTIME_DIRS, "docs/installation", "docs/powers"])
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw workspace init")
    result.add_argument("target", nargs="?", default=".")
    result.add_argument("--id", dest="workspace_id", required=True)
    result.add_argument("--name", required=True)
    result.add_argument("--in-place", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        values = list(argv) if argv is not None else sys.argv[1:]
        if values[:2] == ["workspace", "init"]:
            values = values[2:]
        args = parser().parse_args(values)
        if not registry.PROJECT_ID.fullmatch(args.workspace_id):
            raise registry.ProjectRegistryError(
                f"invalid workspace id: {args.workspace_id!r}"
            )
        if not args.name.strip():
            raise registry.ProjectRegistryError("workspace name cannot be empty")
        return int(registry.workspace_init(args))
    except (registry.ProjectRegistryError, OSError, ValueError, KeyError) as exc:
        print(f"dw-project: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
