from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from .common import (
    MANAGED_MARKER,
    ConsumerError,
    binding_path,
    binding_records,
    distribution_roots,
    history_root,
    installed_root,
    legacy_target_install,
    package_marker,
    refresh_bindings,
    runtime_config_root,
    runtime_root_for,
)
from .install_ops import configured_install
from .package_io import verify_installed_manifest, verify_package


def history_entries(roots: dict[str, Path], power_id: str) -> list[dict[str, Any]]:
    root = history_root(roots, power_id)
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_dir() and (path / MANAGED_MARKER).is_file():
            marker = package_marker(path)
            rows.append(
                {
                    "name": path.name,
                    "version": marker.get("version"),
                    "path": str(path),
                    "modified_epoch": int(path.stat().st_mtime),
                }
            )
    return rows


def history(args: Any) -> dict[str, Any]:
    roots = distribution_roots(args.store_root)
    return {
        "status": "PASS",
        "scope": "workspace-store",
        "power_id": args.power_id,
        "store_root": str(roots["store"]),
        "history": history_entries(roots, args.power_id),
    }


def rollback(args: Any) -> dict[str, Any]:
    roots = distribution_roots(args.store_root)
    current = installed_root(roots, args.power_id)
    if not current.is_dir() or not (current / MANAGED_MARKER).is_file():
        raise ConsumerError(f"managed workspace installation missing: {current}")
    entries = history_entries(roots, args.power_id)
    if args.version:
        entries = [row for row in entries if args.version in (row["version"], row["name"])]
    if not entries:
        raise ConsumerError("no matching managed history entry")
    selected = Path(entries[0]["path"])
    root = history_root(roots, args.power_id)
    backup = root / f"{package_marker(current).get('version', 'unknown')}-rollback-{int(time.time())}"
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = root / f"{backup.name}-{suffix}"
    os.replace(current, backup)
    try:
        os.replace(selected, current)
        package_manifest = verify_package(current, args.power_id)
        verify_installed_manifest(current, package_manifest)
    except Exception:
        if current.exists():
            os.replace(current, selected)
        os.replace(backup, current)
        raise
    bindings = refresh_bindings(roots, args.power_id, current, package_manifest)
    return {
        "status": "ROLLED_BACK",
        "scope": "workspace-store",
        "power_id": args.power_id,
        "version": package_marker(current).get("version"),
        "install_root": str(current),
        "replaced_backup": str(backup),
        "updated_bindings": bindings,
    }


def uninstall(args: Any) -> dict[str, Any]:
    roots, target, package_manifest, install = configured_install(args)
    removed: list[str] = []
    binding = binding_path(roots, target, args.power_id)
    if binding.exists():
        binding.unlink()
        removed.append(str(binding))
        if binding.parent.is_dir() and not any(binding.parent.iterdir()):
            binding.parent.rmdir()
    config = runtime_config_root(target, package_manifest)
    if config.exists():
        if not (config / MANAGED_MARKER).is_file():
            raise ConsumerError(f"refusing to remove unmanaged configuration: {config}")
        shutil.rmtree(config)
        removed.append(str(config))
    runtime = runtime_root_for(target, package_manifest)
    if args.include_runtime:
        if not args.yes:
            raise ConsumerError("--include-runtime requires --yes")
        if runtime.exists():
            shutil.rmtree(runtime)
            removed.append(str(runtime))
    remaining = binding_records(roots, args.power_id)
    package_removed = False
    if not remaining:
        if not (install / MANAGED_MARKER).is_file():
            raise ConsumerError(f"refusing to remove unmanaged package: {install}")
        shutil.rmtree(install)
        removed.append(str(install))
        package_removed = True
    return {
        "status": "UNINSTALLED" if package_removed else "DETACHED",
        "scope": "workspace-store-and-system-binding",
        "power_id": args.power_id,
        "runtime_preserved": not args.include_runtime,
        "package_removed": package_removed,
        "remaining_bindings": [str(path) for path, _ in remaining],
        "removed": removed,
        "legacy": legacy_target_install(target, args.power_id),
    }
