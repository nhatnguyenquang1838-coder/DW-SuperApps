#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dw_cli  # noqa: E402
import clean_power_setup  # noqa: E402
import dw_entry  # noqa: E402
import dw_project_add  # noqa: E402
import dw_project_registry  # noqa: E402
import dw_workspace_dist  # noqa: E402
import dw_workspace_init  # noqa: E402
from dw_power_store.cli import main as power_main  # noqa: E402
from dw_workspace_dist import main as distribution_main  # noqa: E402


def project_add_main(argv: list[str]) -> int:
    original = sys.argv
    try:
        sys.argv = [original[0], *argv[2:]]
        return int(dw_project_add.main())
    finally:
        sys.argv = original


def main() -> int:
    # One-click init/sync/doctor paths load dw_cli internally; patch their host
    # operations to use the workspace distribution store resolver as well.
    dw_cli.install_host_adapters = dw_workspace_dist.host_install
    dw_cli.host_status = dw_workspace_dist.host_status
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "workspace" and argv[1] == "init":
        return int(dw_workspace_init.main(argv))
    if len(argv) >= 2 and argv[0] == "project":
        if argv[1] in {"list", "info"}:
            return int(dw_project_registry.main(argv))
        if argv[1] == "add":
            return project_add_main(argv)
    if len(argv) >= 2 and argv[0] == "power":
        if argv[1] == "cleanup":
            return clean_power_setup.main(argv[2:])
        if argv[1] in {"install", "configure", "sanity", "doctor", "history", "rollback", "uninstall"}:
            return power_main(argv[1:])
    if len(argv) >= 2 and argv[0] == "host" and argv[1] in {"install", "status"}:
        return distribution_main(argv)
    return int(dw_entry.main())


if __name__ == "__main__":
    raise SystemExit(main())
