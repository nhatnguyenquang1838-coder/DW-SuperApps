#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
except ImportError as exc:
    print("Missing PyYAML. Run: python -m pip install -r requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2) from exc

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "manifests" / "powers"
MANAGED_MARKER = ".dw-managed.json"


class ConsumerError(RuntimeError):
    pass


def emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConsumerError(f"missing manifest: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConsumerError(f"expected YAML mapping: {path}")
    return data


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


def safe_extract(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts:
                raise ConsumerError(f"unsafe archive member: {info.filename}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ConsumerError(f"symlink archive member is not allowed: {info.filename}")
        bundle.extractall(destination)

    roots = sorted({path.parent for path in destination.rglob("MANIFEST.json")})
    if len(roots) != 1:
        raise ConsumerError(f"archive must contain exactly one package root; found {len(roots)}")
    return roots[0]


def read_checksum(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip().split()
    if not token or len(token[0]) != 64:
        raise ConsumerError(f"invalid checksum file: {path}")
    return token[0].lower()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "dw-superapps-power-consumer/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            destination.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConsumerError(f"download failed: {url}: {exc}") from exc


def source_urls(data: dict[str, Any], source: str, version: str | None) -> tuple[str, str | None]:
    distribution = data["spec"]["distribution"]
    modes = distribution["modes"]
    if source == "release":
        if not version:
            raise ConsumerError("--version is required for release source")
        config = modes["release"]
        repository = config["repository"]
        asset = config["assetPattern"].format(power_id=data["metadata"]["id"], version=version)
        checksum = config["checksumAssetPattern"].format(
            power_id=data["metadata"]["id"], version=version
        )
        base = f"https://github.com/{repository}/releases/download/{version}"
        return f"{base}/{asset}", f"{base}/{checksum}"
    if source == "power-dist":
        config = modes["powerDist"]
        repository = config["repository"]
        ref = config["ref"]
        return f"https://github.com/{repository}/archive/refs/heads/{ref}.zip", None
    raise ConsumerError(f"source does not use a downloadable package: {source}")


def verify_package(package_root: Path, power_id: str) -> dict[str, Any]:
    manifest_path = package_root / "MANIFEST.json"
    runtime = package_root / "lib" / "power_runtime.py"
    if not manifest_path.is_file() or not runtime.is_file():
        raise ConsumerError("package requires MANIFEST.json and lib/power_runtime.py")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("metadata", {}).get("powerId") != power_id:
        raise ConsumerError(
            f"package power ID mismatch: expected {power_id}, "
            f"found {data.get('metadata', {}).get('powerId')}"
        )
    for entry in data.get("files", []):
        relative = str(entry.get("path", ""))
        path = package_root / relative
        if not path.is_file():
            raise ConsumerError(f"package file missing: {relative}")
        if path.stat().st_size != entry.get("size"):
            raise ConsumerError(f"package file size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise ConsumerError(f"package file checksum mismatch: {relative}")
    return data


def run_runtime(package_root: Path, command: str, target: Path, extra: list[str]) -> dict[str, Any]:
    runtime = package_root / "lib" / "power_runtime.py"
    result = subprocess.run(
        [
            sys.executable,
            str(runtime),
            "--package-root",
            str(package_root),
            command,
            "--target",
            str(target),
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConsumerError((result.stderr or result.stdout).strip() or "package runtime failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ConsumerError("package runtime returned invalid JSON") from exc


def installed_root(target: Path, power_id: str) -> Path:
    return target / ".dw" / "powers" / power_id


def history_root(target: Path, power_id: str) -> Path:
    return target / ".dw" / "history" / power_id


def install(args: argparse.Namespace) -> dict[str, Any]:
    data = manifest(args.power_id)
    target = Path(args.target).resolve()
    source = args.source
    if source == "auto":
        source = data["spec"]["distribution"]["defaultMode"]

    if source == "submodule":
        path = ROOT / data["spec"]["path"]
        if not path.exists():
            raise ConsumerError(
                f"legacy submodule is not initialized: {data['spec']['path']}; "
                f"run `dw power init {args.power_id}`"
            )
        runtime_root = target / data["spec"]["runtimeDataRoot"]
        runtime_root.mkdir(parents=True, exist_ok=True)
        return {
            "status": "LEGACY_SUBMODULE_READY",
            "power_id": args.power_id,
            "source": "submodule",
            "path": str(path),
            "runtime_root": str(runtime_root),
        }

    with tempfile.TemporaryDirectory(prefix=f"dw-{args.power_id}-") as temporary:
        temp = Path(temporary)
        checksum_path: Path | None = None
        if args.package:
            package_input = Path(args.package).expanduser().resolve()
            if not package_input.exists():
                raise ConsumerError(f"package not found: {package_input}")
        else:
            url, checksum_url = source_urls(data, source, args.version)
            package_input = temp / "package.zip"
            download(url, package_input)
            if checksum_url:
                checksum_path = temp / "package.zip.sha256"
                download(checksum_url, checksum_path)

        if args.checksum:
            checksum_path = Path(args.checksum).expanduser().resolve()
            if not checksum_path.is_file():
                raise ConsumerError(f"checksum not found: {checksum_path}")

        if checksum_path:
            expected = read_checksum(checksum_path)
            actual = sha256_file(package_input)
            if expected != actual:
                raise ConsumerError(f"archive checksum mismatch: expected {expected}, found {actual}")

        if package_input.is_dir():
            package_root = package_input
        elif zipfile.is_zipfile(package_input):
            package_root = safe_extract(package_input, temp / "extract")
        else:
            raise ConsumerError("--package must be a package directory or ZIP archive")

        package_manifest = verify_package(package_root, args.power_id)
        result = run_runtime(package_root, "install", target, [])
        result.update(
            {
                "source": source,
                "source_version": args.version,
                "package_version": package_manifest["metadata"]["version"],
            }
        )
        return result


def configure(args: argparse.Namespace) -> dict[str, Any]:
    root = installed_root(Path(args.target).resolve(), args.power_id)
    if not root.is_dir():
        raise ConsumerError(f"Power is not installed: {root}")
    extra: list[str] = []
    if args.config:
        extra.extend(["--config", str(Path(args.config).resolve())])
    if args.contract:
        extra.extend(["--contract", str(Path(args.contract).resolve())])
    return run_runtime(root, "configure", Path(args.target).resolve(), extra)


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target).resolve()
    root = installed_root(target, args.power_id)
    if not root.is_dir():
        data = manifest(args.power_id)
        legacy = ROOT / data["spec"]["path"]
        if legacy.exists():
            runtime = target / data["spec"]["runtimeDataRoot"]
            return {
                "status": "PASS",
                "power_id": args.power_id,
                "mode": "legacy-submodule",
                "source_root": str(legacy),
                "runtime": "ready" if runtime.is_dir() else "missing",
            }
        raise ConsumerError(f"Power is not installed: {root}")
    extra = ["--require-config"] if args.require_config else []
    return run_runtime(root, "doctor", target, extra)


def history_entries(target: Path, power_id: str) -> list[dict[str, Any]]:
    root = history_root(target, power_id)
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_dir() or not (path / MANAGED_MARKER).is_file():
            continue
        marker = json.loads((path / MANAGED_MARKER).read_text(encoding="utf-8"))
        rows.append(
            {
                "name": path.name,
                "version": marker.get("version"),
                "path": str(path),
                "modified_epoch": int(path.stat().st_mtime),
            }
        )
    return rows


def history(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target).resolve()
    return {
        "status": "PASS",
        "power_id": args.power_id,
        "history": history_entries(target, args.power_id),
    }


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target).resolve()
    current = installed_root(target, args.power_id)
    if not current.is_dir() or not (current / MANAGED_MARKER).is_file():
        raise ConsumerError(f"managed installation missing: {current}")
    entries = history_entries(target, args.power_id)
    if args.version:
        entries = [item for item in entries if item["version"] == args.version or item["name"] == args.version]
    if not entries:
        raise ConsumerError("no matching managed history entry")
    selected = Path(entries[0]["path"])
    current_marker = json.loads((current / MANAGED_MARKER).read_text(encoding="utf-8"))
    root = history_root(target, args.power_id)
    root.mkdir(parents=True, exist_ok=True)
    backup = root / f"{current_marker.get('version', 'unknown')}-rollback-{int(time.time())}"
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = root / f"{current_marker.get('version', 'unknown')}-rollback-{int(time.time())}-{suffix}"
    os.replace(current, backup)
    try:
        os.replace(selected, current)
        result = run_runtime(current, "doctor", target, [])
    except Exception:
        if current.exists():
            os.replace(current, selected)
        os.replace(backup, current)
        raise
    result.update({"status": "ROLLED_BACK", "replaced_backup": str(backup)})
    return result


def uninstall(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target).resolve()
    root = installed_root(target, args.power_id)
    if not root.is_dir():
        raise ConsumerError(f"Power is not installed: {root}")
    extra: list[str] = []
    if args.include_runtime:
        extra.append("--include-runtime")
    if args.yes:
        extra.append("--yes")
    return run_runtime(root, "uninstall", target, extra)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw power", description="DW Power package consumer")
    commands = result.add_subparsers(dest="command", required=True)

    install_parser = commands.add_parser("install")
    install_parser.add_argument("power_id")
    install_parser.add_argument("--source", choices=["auto", "submodule", "release", "power-dist", "package"], default="auto")
    install_parser.add_argument("--package")
    install_parser.add_argument("--checksum")
    install_parser.add_argument("--version")
    install_parser.add_argument("--target", default=".")
    install_parser.set_defaults(handler=install)

    configure_parser = commands.add_parser("configure")
    configure_parser.add_argument("power_id")
    configure_parser.add_argument("--config")
    configure_parser.add_argument("--contract")
    configure_parser.add_argument("--target", default=".")
    configure_parser.set_defaults(handler=configure)

    doctor_parser = commands.add_parser("doctor")
    doctor_parser.add_argument("power_id")
    doctor_parser.add_argument("--target", default=".")
    doctor_parser.add_argument("--require-config", action="store_true")
    doctor_parser.set_defaults(handler=doctor)

    history_parser = commands.add_parser("history")
    history_parser.add_argument("power_id")
    history_parser.add_argument("--target", default=".")
    history_parser.set_defaults(handler=history)

    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("power_id")
    rollback_parser.add_argument("--version")
    rollback_parser.add_argument("--target", default=".")
    rollback_parser.set_defaults(handler=rollback)

    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("power_id")
    uninstall_parser.add_argument("--target", default=".")
    uninstall_parser.add_argument("--include-runtime", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")
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


if __name__ == "__main__":
    raise SystemExit(main())
