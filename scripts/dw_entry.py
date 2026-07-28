#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REQUIREMENTS = ROOT / "requirements-dev.txt"
HOSTS = ("kiro", "codex", "copilot", "cline", "kilo", "claude", "custom")
ONECLICK = {"init", "sync", "clean", "status", "doctor", "reset"}


class EntryError(RuntimeError):
    pass


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise EntryError(detail or f"command failed: {' '.join(args)}")
    return result


def load_runtime() -> Any:
    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        return importlib.import_module("dw_cli")
    except SystemExit as exc:
        raise EntryError(
            "Power Runtime dependencies are missing. Run `dw init all`."
        ) from exc


def ns(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def install_dependencies() -> None:
    if not REQUIREMENTS.is_file():
        raise EntryError("missing requirements-dev.txt")
    print("==> Install workspace dependencies")
    run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])


def init_all(args: argparse.Namespace) -> int:
    if not args.skip_deps:
        install_dependencies()
    runtime = load_runtime()
    print(f"==> Initialize submodules: {args.target}")
    result = runtime.power_sync(ns(target=args.target, mode="init"))
    if result:
        return int(result)
    print(f"==> Install host adapters: {args.host}")
    result = runtime.install_host_adapters(ns(host=args.host, mode=args.mode))
    if result:
        return int(result)
    if not args.skip_providers:
        print("==> Install configured model providers")
        result = runtime.provider_install(
            ns(
                provider_id="all",
                model=args.model,
                base_url=None,
                api_key=None,
            )
        )
        if result:
            return int(result)
    print("==> Validate workspace")
    result = runtime.validate(ns())
    if result:
        return int(result)
    print("==> Verify host adapters")
    result = runtime.host_status(ns(host=args.host))
    if result:
        return int(result)
    if not args.skip_providers:
        print("==> Verify providers")
        return int(runtime.provider_status(ns(provider_id="all", probe=False)))
    return 0


def sync_all(args: argparse.Namespace) -> int:
    runtime = load_runtime()
    print(f"==> Update submodules: {args.target}")
    result = runtime.power_sync(ns(target=args.target, mode="update"))
    if result:
        return int(result)
    if args.pin:
        print(f"==> Stage updated pins: {args.target}")
        result = runtime.power_sync(ns(target=args.target, mode="pin"))
        if result:
            return int(result)
    print(f"==> Refresh host adapters: {args.host}")
    result = runtime.install_host_adapters(ns(host=args.host, mode=args.mode))
    if result:
        return int(result)
    if args.skip_validate:
        return 0
    print("==> Validate workspace")
    return int(runtime.validate(ns()))


def clean_adapters() -> int:
    runtime = load_runtime()
    removed = int(runtime.remove_host_adapters("all"))
    print(f"Removed generated host adapters: {removed}")
    return removed


def clean_caches() -> int:
    removed = 0
    for path in (ROOT / ".pytest_cache", ROOT / ".mypy_cache", ROOT / ".ruff_cache"):
        if path.is_dir():
            shutil.rmtree(path)
            removed += 1
        elif path.is_file():
            path.unlink()
            removed += 1
    for path in sorted(ROOT.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
            removed += 1
    for path in ROOT.rglob("*.pyc"):
        if path.is_file():
            path.unlink()
            removed += 1
    print(f"Removed cache entries: {removed}")
    return removed


def runtime_paths(runtime: Any) -> list[Path]:
    workspace = runtime.workspace()
    roots = list((workspace.get("data_ownership") or {}).get("roots", {}).values())
    paths: list[Path] = []
    for system in workspace.get("systems", []):
        system_root = ROOT / system["path"]
        for name in roots:
            path = system_root / str(name)
            try:
                path.absolute().relative_to(system_root.absolute())
            except ValueError as exc:
                raise EntryError(f"unsafe runtime path: {path}") from exc
            paths.append(path)
    return paths


def clean_runtime(*, confirmed: bool) -> int:
    if not confirmed:
        raise EntryError("runtime cleanup requires --yes")
    runtime = load_runtime()
    removed = 0
    for path in runtime_paths(runtime):
        if path.is_symlink() or path.is_file():
            path.unlink()
            removed += 1
        elif path.is_dir():
            shutil.rmtree(path)
            removed += 1
    print(f"Removed runtime roots: {removed}")
    return removed


def clean_plan(scope: str, include_runtime: bool = False) -> set[str]:
    if scope == "all":
        plan = {"adapters", "cache"}
    elif scope in {"adapters", "cache", "runtime"}:
        plan = {scope}
    else:
        raise EntryError(f"unknown clean scope: {scope}")
    if include_runtime:
        plan.add("runtime")
    return plan


def clean_all(args: argparse.Namespace) -> int:
    plan = clean_plan(args.scope, args.include_runtime)
    print(f"==> Clean: {', '.join(sorted(plan))}")
    if "adapters" in plan:
        clean_adapters()
    if "cache" in plan:
        clean_caches()
    if "runtime" in plan:
        clean_runtime(confirmed=args.yes)
    elif args.scope == "all":
        print("Runtime data preserved. Add --include-runtime --yes to remove it.")
    return 0


def status_all(args: argparse.Namespace) -> int:
    runtime = load_runtime()
    runtime.workspace_info(ns(json=False))
    print("\nSubmodules:")
    result = runtime.power_sync(ns(target=args.target, mode="status"))
    print("\nHost adapters:")
    host_result = runtime.host_status(ns(host=args.host))
    print("\nProviders:")
    provider_result = runtime.provider_status(ns(provider_id="all", probe=False))
    return 1 if result or host_result or provider_result else 0


def doctor_all(args: argparse.Namespace) -> int:
    runtime = load_runtime()
    failed = False
    runtime.workspace_info(ns(json=False))
    print("\nWorkspace contract:")
    failed = bool(runtime.validate(ns())) or failed
    print("\nSubmodule health:")
    mode = "status" if args.offline else "check"
    failed = bool(runtime.power_sync(ns(target=args.target, mode=mode))) or failed
    print("\nHost adapters:")
    failed = bool(runtime.host_status(ns(host=args.host))) or failed
    print("\nProviders:")
    failed = bool(
        runtime.provider_status(
            ns(provider_id="all", probe=args.probe_providers)
        )
    ) or failed
    return 1 if failed else 0


def reset_all(args: argparse.Namespace) -> int:
    if not args.yes:
        raise EntryError("reset requires --yes")
    runtime = load_runtime()
    selected = runtime.select_submodules(args.target)
    paths = [item["path"] for item in selected]
    for path in paths:
        absolute = ROOT / path
        if (absolute / ".git").exists():
            dirty = run(
                ["git", "-C", path, "status", "--porcelain"],
                capture=True,
            ).stdout.strip()
            if dirty:
                raise EntryError(f"refusing to reset dirty submodule {path}")
    print(f"==> Deinitialize submodules: {args.target}")
    run(["git", "submodule", "deinit", "-f", "--", *paths])
    clean_adapters()
    clean_caches()
    print("Reset complete. Run `dw init all` to rebuild.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dw",
        description="DW SuperApps one-click workspace commands",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser(
        "init",
        help="bootstrap dependencies, submodules, hosts, providers, validation",
    )
    init_parser.add_argument("target", nargs="?", default="all")
    init_parser.add_argument("--host", choices=[*HOSTS, "all"], default="all")
    init_parser.add_argument("--mode", choices=["wrapper", "link", "copy"], default="wrapper")
    init_parser.add_argument("--skip-deps", action="store_true")
    init_parser.add_argument("--skip-providers", action="store_true")
    init_parser.add_argument("--model", help="override the configured local provider model")
    init_parser.set_defaults(handler=init_all)

    sync_parser = commands.add_parser(
        "sync",
        help="update submodules, refresh hosts, validate",
    )
    sync_parser.add_argument("target", nargs="?", default="all")
    sync_parser.add_argument("--pin", action="store_true")
    sync_parser.add_argument("--host", choices=[*HOSTS, "all"], default="all")
    sync_parser.add_argument("--mode", choices=["wrapper", "link", "copy"], default="wrapper")
    sync_parser.add_argument("--skip-validate", action="store_true")
    sync_parser.set_defaults(handler=sync_all)

    clean_parser = commands.add_parser(
        "clean",
        help="remove generated adapters and caches safely",
    )
    clean_parser.add_argument(
        "scope",
        nargs="?",
        choices=["all", "adapters", "cache", "runtime"],
        default="all",
    )
    clean_parser.add_argument("--include-runtime", action="store_true")
    clean_parser.add_argument("--yes", action="store_true")
    clean_parser.set_defaults(handler=clean_all)

    status_parser = commands.add_parser(
        "status",
        help="show workspace, submodules, hosts, and providers",
    )
    status_parser.add_argument("target", nargs="?", default="all")
    status_parser.add_argument("--host", choices=[*HOSTS, "all"], default="all")
    status_parser.set_defaults(handler=status_all)

    doctor_parser = commands.add_parser(
        "doctor",
        help="validate contract, submodules, hosts, and providers",
    )
    doctor_parser.add_argument("target", nargs="?", default="all")
    doctor_parser.add_argument("--host", choices=[*HOSTS, "all"], default="all")
    doctor_parser.add_argument("--offline", action="store_true")
    doctor_parser.add_argument("--probe-providers", action="store_true")
    doctor_parser.set_defaults(handler=doctor_all)

    reset_parser = commands.add_parser(
        "reset",
        help="deinitialize clean submodules and generated files",
    )
    reset_parser.add_argument("target", nargs="?", default="all")
    reset_parser.add_argument("--yes", action="store_true")
    reset_parser.set_defaults(handler=reset_all)
    return parser


def main() -> int:
    argv = sys.argv[1:]
    if argv == ["--version"]:
        print("dw 2.3")
        return 0
    if not argv or argv[0] not in ONECLICK:
        runtime = load_runtime()
        return int(runtime.main())
    try:
        args = build_parser().parse_args(argv)
        return int(args.handler(args))
    except EntryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
