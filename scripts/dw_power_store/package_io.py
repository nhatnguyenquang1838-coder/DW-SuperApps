from __future__ import annotations

import os
import shutil
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .common import (
    MANAGED_MARKER,
    ConsumerError,
    atomic_json,
    load_json,
    package_marker,
    sha256_file,
)


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


def discover_local_package(roots: dict[str, Path], power_id: str) -> tuple[Path, Path]:
    inbox = roots["inbox"] / power_id
    archives = sorted(inbox.glob("*.zip")) if inbox.is_dir() else []
    if not archives:
        raise ConsumerError(f"BLOCKED_LOCAL_PACKAGE_MISSING: {inbox}")
    if len(archives) != 1:
        raise ConsumerError(f"BLOCKED_LOCAL_PACKAGE_AMBIGUOUS: {inbox}")
    archive = archives[0]
    checksum = archive.with_name(archive.name + ".sha256")
    if not checksum.is_file():
        raise ConsumerError(f"BLOCKED_LOCAL_CHECKSUM_MISSING: {archive}")
    return archive, checksum


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "dw-superapps-power-consumer/2"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            destination.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConsumerError(f"download failed: {url}: {exc}") from exc


def source_urls(data: dict[str, Any], source: str, version: str | None) -> tuple[str, str | None]:
    modes = data["spec"]["distribution"]["modes"]
    if source == "release":
        if not version:
            raise ConsumerError("--version is required for release source")
        config = modes["release"]
        base = f"https://github.com/{config['repository']}/releases/download/{version}"
        asset = config["assetPattern"].format(power_id=data["metadata"]["id"], version=version)
        checksum = config["checksumAssetPattern"].format(
            power_id=data["metadata"]["id"], version=version
        )
        return f"{base}/{asset}", f"{base}/{checksum}"
    if source == "power-dist":
        config = modes["powerDist"]
        return (
            f"https://github.com/{config['repository']}/archive/refs/heads/{config['ref']}.zip",
            None,
        )
    raise ConsumerError(f"source does not use a downloadable package: {source}")


def verify_package(package_root: Path, power_id: str) -> dict[str, Any]:
    manifest_path = package_root / "MANIFEST.json"
    runtime = package_root / "lib" / "power_runtime.py"
    if not manifest_path.is_file() or not runtime.is_file():
        raise ConsumerError("package requires MANIFEST.json and lib/power_runtime.py")
    data = load_json(manifest_path)
    if data.get("metadata", {}).get("powerId") != power_id:
        raise ConsumerError(f"package power ID mismatch: expected {power_id}")
    for entry in data.get("files", []):
        path = package_root / str(entry.get("path", ""))
        if not path.is_file() or path.stat().st_size != entry.get("size"):
            raise ConsumerError(f"package file missing or size mismatch: {entry.get('path')}")
        if sha256_file(path) != entry.get("sha256"):
            raise ConsumerError(f"package file checksum mismatch: {entry.get('path')}")
    runtime_root = Path(str(data.get("spec", {}).get("runtimeDataRoot", "")))
    if not str(runtime_root) or runtime_root.is_absolute() or ".." in runtime_root.parts:
        raise ConsumerError("package runtimeDataRoot must be a safe relative path")
    return data


def verify_installed_manifest(install: Path, package_manifest: dict[str, Any]) -> None:
    for entry in package_manifest.get("files", []):
        path = install / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise ConsumerError(f"installed file missing or size mismatch: {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise ConsumerError(f"installed hash mismatch: {entry['path']}")
    for entrypoint in package_manifest.get("spec", {}).get("entrypoints", []):
        if not (install / entrypoint).is_file():
            raise ConsumerError(f"entrypoint missing: {entrypoint}")


def install_package_tree(
    source: Path, destination: Path, history: Path, package_manifest: dict[str, Any]
) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)
    previous = package_marker(destination) if destination.exists() else None
    if destination.exists() and not (destination / MANAGED_MARKER).is_file():
        raise ConsumerError(f"refusing to overwrite unmanaged installation: {destination}")
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    backup: Path | None = None
    try:
        shutil.copytree(source, temporary, symlinks=False)
        atomic_json(
            temporary / MANAGED_MARKER,
            {
                "managedBy": "dw-superapps-power-store",
                "powerId": package_manifest["metadata"]["powerId"],
                "version": package_manifest["metadata"]["version"],
                "sourceManifestSha256": sha256_file(source / "MANIFEST.json"),
                "installedAtEpoch": int(time.time()),
            },
        )
        if destination.exists():
            version = str((previous or {}).get("version", "unknown"))
            backup = history / f"{version}-{int(time.time())}"
            suffix = 0
            while backup.exists():
                suffix += 1
                backup = history / f"{version}-{int(time.time())}-{suffix}"
            os.replace(destination, backup)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if backup and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    return backup


def materialize_package(
    data: dict[str, Any], args: Any, roots: dict[str, Path], temporary: Path
) -> tuple[Path, str]:
    source = args.source
    if source == "auto":
        source = data["spec"]["distribution"]["defaultMode"]
    if source == "submodule":
        from .common import ROOT

        root = ROOT / data["spec"]["path"]
        if not (root / "MANIFEST.json").is_file():
            raise ConsumerError("submodule source is not a distribution package")
        return root, source

    checksum: Path | None = None
    if args.package:
        package = Path(args.package).expanduser().resolve()
        if not package.exists():
            raise ConsumerError(f"package not found: {package}")
    elif source == "package":
        package, checksum = discover_local_package(roots, args.power_id)
    else:
        url, checksum_url = source_urls(data, source, args.version)
        package = temporary / "package.zip"
        download(url, package)
        if checksum_url:
            checksum = temporary / "package.zip.sha256"
            download(checksum_url, checksum)
    if args.checksum:
        checksum = Path(args.checksum).expanduser().resolve()
    if checksum:
        if not checksum.is_file():
            raise ConsumerError(f"checksum not found: {checksum}")
        expected, actual = read_checksum(checksum), sha256_file(package)
        if expected != actual:
            raise ConsumerError(f"archive checksum mismatch: expected {expected}, found {actual}")
    if package.is_dir():
        return package, source
    if zipfile.is_zipfile(package):
        return safe_extract(package, temporary / "extract"), source
    raise ConsumerError("--package must be a package directory or ZIP archive")
