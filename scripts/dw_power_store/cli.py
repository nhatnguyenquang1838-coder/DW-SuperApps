from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .common import ConsumerError
from .history_ops import history, rollback, uninstall
from .install_ops import configure, doctor, install
from .package_io import safe_extract


def emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw power", description="DW Power package consumer")
    commands = result.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser, *, target: bool = True) -> None:
        if target:
            command.add_argument("--target", default=".")
        command.add_argument(
            "--store-root",
            help="override workspace package store (default: workspace.yaml distribution.storeRoot)",
        )

    install_parser = commands.add_parser("install")
    install_parser.add_argument("power_id")
    install_parser.add_argument(
        "--source",
        choices=["auto", "submodule", "release", "power-dist", "package"],
        default="auto",
    )
    install_parser.add_argument("--package")
    install_parser.add_argument("--checksum")
    install_parser.add_argument("--version")
    common(install_parser)
    install_parser.set_defaults(handler=install)

    configure_parser = commands.add_parser("configure")
    configure_parser.add_argument("power_id")
    configure_parser.add_argument("--config")
    configure_parser.add_argument("--contract")
    common(configure_parser)
    configure_parser.set_defaults(handler=configure)

    doctor_parser = commands.add_parser("doctor")
    doctor_parser.add_argument("power_id")
    doctor_parser.add_argument("--require-config", action="store_true")
    common(doctor_parser)
    doctor_parser.set_defaults(handler=doctor)

    history_parser = commands.add_parser("history")
    history_parser.add_argument("power_id")
    common(history_parser, target=False)
    history_parser.set_defaults(handler=history)

    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("power_id")
    rollback_parser.add_argument("--version")
    common(rollback_parser, target=False)
    rollback_parser.set_defaults(handler=rollback)

    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("power_id")
    uninstall_parser.add_argument("--include-runtime", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")
    common(uninstall_parser)
    uninstall_parser.set_defaults(handler=uninstall)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        emit(args.handler(args))
        return 0
    except (ConsumerError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"dw-power: {exc}", file=sys.stderr)
        return 2


__all__ = [
    "ConsumerError",
    "configure",
    "doctor",
    "history",
    "install",
    "main",
    "parser",
    "rollback",
    "safe_extract",
    "uninstall",
]
