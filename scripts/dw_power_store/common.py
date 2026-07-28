from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_PATH = ROOT / "workspace.yaml"
MANIFEST_DIR = ROOT / "manifests" / "powers"
MANAGED_MARKER = ".dw-managed.json"
BINDING_SCHEMA = "dw.superapps/power-binding/v1"


class ConsumerError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConsumerError(f"missing manifest: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConsumerError(f"expected YAML mapping: {path}")
    return data


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConsumerError(f"required file missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConsumerError(f"expected JSON object: {path}")
    return data


def workspace() -> dict[str, Any]:
    return load_yaml(WORKSPACE_PATH)


def manifest(power_id: str) -> dict[str, Any]:
    data = load_yaml(MANIFEST_DIR / f"{power_id}.yaml")
    if data.get("metadata", {}).get("id") != power_id:
        raise ConsumerError(f"manifest identity mismatch for {power_id}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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


def resolve_workspace_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def distribution_roots(store_root: str | Path | None = None) -> dict[str, Path]:
    distribution = workspace().get("distribution") or {}
    if not isinstance(distribution, dict):
        raise ConsumerError("workspace distribution must be a mapping")
    if store_root:
        store = resolve_workspace_path(store_root)
        dw_root = store.parent
        return {
            "store": store,
            "inbox": dw_root / "inbox" / "powers",
            "cache": dw_root / "cache",
            "history": dw_root / "history" / "powers",
            "bindings": dw_root / "bindings",
        }

    def configured(name: str, default: str) -> Path:
        value = distribution.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise ConsumerError(f"workspace distribution.{name} must be a path string")
        return resolve_workspace_path(value)

    return {
        "store": configured("storeRoot", ".dw/powers"),
        "inbox": configured("inboxRoot", ".dw/inbox/powers"),
        "cache": configured("cacheRoot", ".dw/cache"),
        "history": configured("historyRoot", ".dw/history/powers"),
        "bindings": configured("bindingsRoot", ".dw/bindings"),
    }


def validate_store_target_separation(roots: dict[str, Path], target: Path) -> None:
    store = roots["store"].resolve()
    target = target.resolve()
    if store == target or is_within(store, target) or is_within(target, store):
        raise ConsumerError("BLOCKED_STORE_RUNTIME_OVERLAP: package store and system target overlap")
    for name, path in roots.items():
        if is_within(path, target):
            raise ConsumerError(
                f"BLOCKED_STORE_INSIDE_SYSTEM: distribution {name} root resolves inside {target}"
            )


def installed_root(roots: dict[str, Path], power_id: str) -> Path:
    return roots["store"] / power_id


def history_root(roots: dict[str, Path], power_id: str) -> Path:
    return roots["history"] / power_id


def runtime_root_for(target: Path, package_manifest: dict[str, Any]) -> Path:
    relative = Path(str(package_manifest["spec"]["runtimeDataRoot"]))
    runtime = (target / relative).resolve()
    if relative.is_absolute() or not is_within(runtime, target):
        raise ConsumerError("runtime data root escapes system target")
    return runtime


def runtime_config_root(target: Path, package_manifest: dict[str, Any]) -> Path:
    return runtime_root_for(target, package_manifest) / "config"


def target_key(target: Path) -> str:
    target = target.resolve()
    for system in workspace().get("systems", []):
        if isinstance(system, dict) and (ROOT / str(system.get("path", ""))).resolve() == target:
            return str(system["id"])
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:12]
    return f"external-{digest}"


def binding_path(roots: dict[str, Path], target: Path, power_id: str) -> Path:
    return roots["bindings"] / target_key(target) / f"{power_id}.json"


def binding_records(roots: dict[str, Path], power_id: str) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    if not roots["bindings"].is_dir():
        return rows
    for path in sorted(roots["bindings"].glob(f"*/{power_id}.json")):
        rows.append((path, load_json(path)))
    return rows


def package_marker(install: Path) -> dict[str, Any]:
    return load_json(install / MANAGED_MARKER)


def legacy_target_install(target: Path, power_id: str) -> dict[str, Any]:
    path = target / ".dw" / "powers" / power_id
    if not path.exists():
        return {"status": "NONE", "path": str(path)}
    return {
        "status": "LEGACY_TARGET_INSTALL",
        "path": str(path),
        "managed": (path / MANAGED_MARKER).is_file(),
        "action": "preserved",
    }


def write_binding(
    roots: dict[str, Path],
    target: Path,
    install: Path,
    package_manifest: dict[str, Any],
    **extra: Any,
) -> Path:
    runtime = runtime_root_for(target, package_manifest)
    marker = package_marker(install)
    path = binding_path(roots, target, package_manifest["metadata"]["powerId"])
    payload: dict[str, Any] = {
        "apiVersion": BINDING_SCHEMA,
        "systemId": target_key(target),
        "targetPath": str(target.resolve()),
        "powerId": package_manifest["metadata"]["powerId"],
        "packageVersion": marker.get("version"),
        "packageManifestSha256": marker.get("sourceManifestSha256"),
        "storePath": str(install.resolve()),
        "runtimePath": str(runtime),
        "updatedAtEpoch": int(time.time()),
    }
    if path.is_file():
        current = load_json(path)
        for key in ("configured", "configPath"):
            if key in current:
                payload[key] = current[key]
    payload.update(extra)
    atomic_json(path, payload)
    return path


def refresh_bindings(
    roots: dict[str, Path], power_id: str, install: Path, package_manifest: dict[str, Any]
) -> list[str]:
    updated: list[str] = []
    marker = package_marker(install)
    for path, data in binding_records(roots, power_id):
        data.update(
            {
                "packageVersion": marker.get("version"),
                "packageManifestSha256": marker.get("sourceManifestSha256"),
                "storePath": str(install.resolve()),
                "updatedAtEpoch": int(time.time()),
            }
        )
        atomic_json(path, data)
        updated.append(str(path))
    return updated
