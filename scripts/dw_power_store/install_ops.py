from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .common import (
    MANAGED_MARKER,
    ConsumerError,
    atomic_json,
    binding_path,
    distribution_roots,
    installed_root,
    legacy_target_install,
    load_json,
    manifest,
    package_marker,
    refresh_bindings,
    runtime_config_root,
    runtime_root_for,
    validate_store_target_separation,
    write_binding,
)
from .package_io import (
    install_package_tree,
    materialize_package,
    verify_installed_manifest,
    verify_package,
)
from .compatibility import sanity


def install(args: Any) -> dict[str, Any]:
    data = manifest(args.power_id)
    target = Path(args.target).expanduser().resolve()
    roots = distribution_roots(args.store_root)
    validate_store_target_separation(roots, target)
    with tempfile.TemporaryDirectory(prefix=f"dw-{args.power_id}-") as temporary:
        package_root, source = materialize_package(data, args, roots, Path(temporary))
        package_manifest = verify_package(package_root, args.power_id)
        destination = installed_root(roots, args.power_id)
        backup = install_package_tree(
            package_root, destination, roots["history"] / args.power_id, package_manifest
        )
    refresh_bindings(roots, args.power_id, destination, package_manifest)
    runtime = runtime_root_for(target, package_manifest)
    runtime.mkdir(parents=True, exist_ok=True)
    binding = write_binding(roots, target, destination, package_manifest)
    return {
        "status": "INSTALLED",
        "power_id": args.power_id,
        "source": source,
        "source_version": args.version,
        "package_version": package_manifest["metadata"]["version"],
        "workspace_root": str(destination.parents[2]),
        "store_root": str(roots["store"]),
        "install_root": str(destination),
        "runtime_target": str(target),
        "runtime_root": str(runtime),
        "binding": str(binding),
        "backup": str(backup) if backup else None,
        "legacy": legacy_target_install(target, args.power_id),
    }


def configured_install(args: Any) -> tuple[dict[str, Path], Path, dict[str, Any], Path]:
    target = Path(args.target).expanduser().resolve()
    roots = distribution_roots(args.store_root)
    validate_store_target_separation(roots, target)
    install = installed_root(roots, args.power_id)
    if not install.is_dir() or not (install / MANAGED_MARKER).is_file():
        raise ConsumerError(f"Power is not installed in workspace store: {install}")
    return roots, target, verify_package(install, args.power_id), install


def configure(args: Any) -> dict[str, Any]:
    roots, target, package_manifest, install = configured_install(args)
    if not args.config and not args.contract:
        raise ConsumerError("configure requires --config and/or --contract")
    destination = runtime_config_root(target, package_manifest)
    if destination.exists() and not (destination / MANAGED_MARKER).is_file():
        raise ConsumerError(f"refusing to overwrite unmanaged configuration: {destination}")
    temporary = destination.parent / f".config-{uuid.uuid4().hex}"
    temporary.mkdir(parents=True, exist_ok=False)
    old: Path | None = None
    try:
        for supplied, name in ((args.config, "config.yaml"), (args.contract, "consumer-contract.yaml")):
            if supplied:
                source = Path(supplied).expanduser().resolve()
                if not source.is_file():
                    raise ConsumerError(f"configuration input not found: {source}")
                shutil.copyfile(source, temporary / name)
            elif destination.is_dir() and (destination / name).is_file():
                shutil.copyfile(destination / name, temporary / name)
        atomic_json(
            temporary / MANAGED_MARKER,
            {
                "managedBy": "dw-superapps-runtime-config",
                "powerId": args.power_id,
                "packageVersion": package_manifest["metadata"]["version"],
                "configuredAtEpoch": int(time.time()),
            },
        )
        if destination.exists():
            old = destination.parent / f".config-old-{uuid.uuid4().hex}"
            os.replace(destination, old)
        os.replace(temporary, destination)
        if old:
            shutil.rmtree(old)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if old and old.exists() and not destination.exists():
            os.replace(old, destination)
        raise
    binding = write_binding(
        roots,
        target,
        install,
        package_manifest,
        configured=True,
        configPath=str(destination),
    )
    return {
        "status": "CONFIGURED",
        "power_id": args.power_id,
        "store_root": str(roots["store"]),
        "install_root": str(install),
        "runtime_target": str(target),
        "runtime_root": str(runtime_root_for(target, package_manifest)),
        "config_root": str(destination),
        "binding": str(binding),
        "legacy": legacy_target_install(target, args.power_id),
    }


def doctor(args: Any) -> dict[str, Any]:
    roots, target, package_manifest, install = configured_install(args)
    compatibility = sanity(args)
    marker = package_marker(install)
    if marker.get("powerId") != args.power_id:
        raise ConsumerError("managed marker power ID mismatch")
    verify_installed_manifest(install, package_manifest)
    runtime = runtime_root_for(target, package_manifest)
    if not runtime.is_dir():
        raise ConsumerError(f"runtime root missing: {runtime}")
    config = runtime_config_root(target, package_manifest)
    configuration = "missing"
    if config.is_dir():
        if load_json(config / MANAGED_MARKER).get("powerId") != args.power_id:
            raise ConsumerError("configuration marker power ID mismatch")
        configuration = "managed"
    elif args.require_config:
        raise ConsumerError("managed configuration is required but missing")
    binding = binding_path(roots, target, args.power_id)
    if not binding.is_file():
        raise ConsumerError(f"workspace binding missing: {binding}")
    data = load_json(binding)
    checks = {
        "storePath": str(install.resolve()),
        "runtimePath": str(runtime),
        "packageVersion": marker.get("version"),
        "packageManifestSha256": marker.get("sourceManifestSha256"),
    }
    for field, expected in checks.items():
        if data.get(field) != expected:
            raise ConsumerError(f"binding {field} mismatch")
    return {
        "status": "PASS",
        "power_id": args.power_id,
        "version": marker.get("version"),
        "store": {"status": "PASS", "path": str(roots["store"])},
        "package": {"status": "PASS", "path": str(install)},
        "binding": {"status": "managed", "path": str(binding)},
        "runtime": {"status": "PASS", "path": str(runtime)},
        "configuration": configuration,
        "compatibility": compatibility,
        "legacy": legacy_target_install(target, args.power_id),
    }
