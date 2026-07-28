#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

MANAGED_MARKER = ".dw-managed.json"


class RuntimeError_(RuntimeError):
    pass


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError_(f"required file missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError_(f"expected object in {path}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def metadata(root: Path) -> dict[str, Any]:
    manifest = load_json(root / "MANIFEST.json")
    return {
        "power_id": manifest["metadata"]["powerId"],
        "version": manifest["metadata"]["version"],
        "runtime_root": manifest["spec"]["runtimeDataRoot"],
        "manifest": manifest,
    }


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8", newline="\n"
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = handle.name
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def resolve_store_root(value: str | None) -> Path:
    raw = value or os.environ.get("DW_POWER_STORE_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    current = package_root().resolve()
    if current.parent.name == "powers" and current.parent.parent.name == ".dw":
        return current.parent
    raise RuntimeError_(
        "--store-root or DW_POWER_STORE_ROOT is required outside an installed workspace package"
    )


def target_paths(target: Path, info: dict[str, Any], store_root: Path) -> dict[str, Path]:
    runtime = (target / info["runtime_root"]).resolve()
    if not is_within(runtime, target.resolve()):
        raise RuntimeError_("runtime data root escapes system target")
    return {
        "target": target.resolve(),
        "store": store_root.resolve(),
        "install": store_root.resolve() / info["power_id"],
        "history": store_root.resolve().parent / "history" / "powers" / info["power_id"],
        "runtime": runtime,
        "config": runtime / "config",
    }


def assert_separated(source: Path, target: Path, store: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    store = store.resolve()
    if store == target or is_within(store, target) or is_within(target, store):
        raise RuntimeError_("package store and system target must not overlap")
    if source == target or is_within(target, source):
        raise RuntimeError_("package source and system target must not overlap")


def marker(path: Path) -> dict[str, Any]:
    return load_json(path / MANAGED_MARKER)


def install(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).expanduser().resolve()
    store = resolve_store_root(args.store_root)
    info = metadata(source)
    paths = target_paths(target, info, store)
    assert_separated(source, target, store)
    destination = paths["install"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths["history"].mkdir(parents=True, exist_ok=True)

    old_marker: dict[str, Any] | None = None
    if destination.exists():
        if not (destination / MANAGED_MARKER).is_file():
            raise RuntimeError_(f"refusing to overwrite unmanaged installation: {destination}")
        old_marker = marker(destination)

    temporary = destination.parent / f".{info['power_id']}.tmp-{uuid.uuid4().hex}"
    backup: Path | None = None
    try:
        shutil.copytree(source, temporary, symlinks=False)
        atomic_json(
            temporary / MANAGED_MARKER,
            {
                "managedBy": "dw-superapps-power-store",
                "powerId": info["power_id"],
                "version": info["version"],
                "sourceManifestSha256": sha256_file(source / "MANIFEST.json"),
                "installedAtEpoch": int(time.time()),
            },
        )
        if destination.exists():
            old_version = str((old_marker or {}).get("version", "unknown"))
            backup = paths["history"] / f"{old_version}-{int(time.time())}"
            os.replace(destination, backup)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if backup and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise

    paths["runtime"].mkdir(parents=True, exist_ok=True)
    return {
        "status": "INSTALLED",
        "power_id": info["power_id"],
        "version": info["version"],
        "store_root": str(store),
        "install_root": str(destination),
        "runtime_target": str(target),
        "runtime_root": str(paths["runtime"]),
        "backup": str(backup) if backup else None,
    }


def configure(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).expanduser().resolve()
    store = resolve_store_root(args.store_root)
    info = metadata(source)
    paths = target_paths(target, info, store)
    if not args.config and not args.contract:
        raise RuntimeError_("configure requires --config and/or --contract")
    destination = paths["config"]
    if destination.exists() and not (destination / MANAGED_MARKER).is_file():
        raise RuntimeError_(f"refusing to overwrite unmanaged configuration: {destination}")

    temporary = destination.parent / f".config-{uuid.uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        if args.config:
            config = Path(args.config).expanduser().resolve()
            if not config.is_file():
                raise RuntimeError_(f"config file not found: {config}")
            shutil.copyfile(config, temporary / "config.yaml")
        if args.contract:
            contract = Path(args.contract).expanduser().resolve()
            if not contract.is_file():
                raise RuntimeError_(f"contract file not found: {contract}")
            shutil.copyfile(contract, temporary / "consumer-contract.yaml")
        atomic_json(
            temporary / MANAGED_MARKER,
            {
                "managedBy": "dw-superapps-runtime-config",
                "powerId": info["power_id"],
                "packageVersion": info["version"],
                "configuredAtEpoch": int(time.time()),
            },
        )
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "status": "CONFIGURED",
        "store_root": str(store),
        "runtime_root": str(paths["runtime"]),
        "config_root": str(destination),
    }


def verify_manifest(install_root: Path, manifest: dict[str, Any]) -> None:
    for entry in manifest.get("files", []):
        path = install_root / entry["path"]
        if not path.is_file():
            raise RuntimeError_(f"installed file missing: {entry['path']}")
        if path.stat().st_size != entry["size"] or sha256_file(path) != entry["sha256"]:
            raise RuntimeError_(f"installed package integrity mismatch: {entry['path']}")
    for entrypoint in manifest.get("spec", {}).get("entrypoints", []):
        if not (install_root / entrypoint).is_file():
            raise RuntimeError_(f"entrypoint missing: {entrypoint}")


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).expanduser().resolve()
    store = resolve_store_root(args.store_root)
    info = metadata(source)
    paths = target_paths(target, info, store)
    install_root = paths["install"]
    if not install_root.is_dir():
        raise RuntimeError_(f"Power is not installed in workspace store: {install_root}")
    installed_marker = marker(install_root)
    installed_manifest = load_json(install_root / "MANIFEST.json")
    verify_manifest(install_root, installed_manifest)
    if not paths["runtime"].is_dir():
        raise RuntimeError_(f"runtime root missing: {paths['runtime']}")
    configuration = "managed" if paths["config"].is_dir() else "missing"
    if args.require_config and configuration == "missing":
        raise RuntimeError_("managed configuration is required but missing")
    return {
        "status": "PASS",
        "power_id": info["power_id"],
        "version": installed_marker.get("version"),
        "store_root": str(store),
        "install_root": str(install_root),
        "runtime_root": str(paths["runtime"]),
        "configuration": configuration,
    }


def uninstall(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.package_root).resolve()
    target = Path(args.target).expanduser().resolve()
    store = resolve_store_root(args.store_root)
    info = metadata(source)
    paths = target_paths(target, info, store)
    removed: list[str] = []
    if paths["config"].exists():
        if not (paths["config"] / MANAGED_MARKER).is_file():
            raise RuntimeError_(f"refusing to remove unmanaged configuration: {paths['config']}")
        shutil.rmtree(paths["config"])
        removed.append(str(paths["config"]))
    if args.include_runtime:
        if not args.yes:
            raise RuntimeError_("--include-runtime requires --yes")
        if paths["runtime"].exists():
            shutil.rmtree(paths["runtime"])
            removed.append(str(paths["runtime"]))
    # Shared package deletion is coordinated by the workspace consumer, which
    # can inspect every system binding. A package-local runtime may detach only.
    return {
        "status": "DETACHED",
        "power_id": info["power_id"],
        "runtime_preserved": not args.include_runtime,
        "package_preserved": True,
        "install_root": str(paths["install"]),
        "removed": removed,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Portable runtime for a DW Power package.")
    result.add_argument("--package-root", default=str(package_root()))
    subparsers = result.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--target", required=True)
        command.add_argument("--store-root")

    install_parser = subparsers.add_parser("install")
    common(install_parser)
    install_parser.set_defaults(handler=install)

    configure_parser = subparsers.add_parser("configure")
    common(configure_parser)
    configure_parser.add_argument("--config")
    configure_parser.add_argument("--contract")
    configure_parser.set_defaults(handler=configure)

    doctor_parser = subparsers.add_parser("doctor")
    common(doctor_parser)
    doctor_parser.add_argument("--require-config", action="store_true")
    doctor_parser.set_defaults(handler=doctor)

    uninstall_parser = subparsers.add_parser("uninstall")
    common(uninstall_parser)
    uninstall_parser.add_argument("--include-runtime", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")
    uninstall_parser.set_defaults(handler=uninstall)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = args.handler(args)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (RuntimeError_, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"power-runtime: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
