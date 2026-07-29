#!/usr/bin/env python3
"""Verify and install DW SUPER offline release assets into a workspace store."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_safe_archive(archive: zipfile.ZipFile) -> None:
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or "../" in name or name == "..":
            raise SystemExit(f"unsafe archive path: {info.filename}")
        mode = info.external_attr >> 16
        if mode & 0o120000 == 0o120000:
            raise SystemExit(f"archive symlink rejected: {info.filename}")


def next_history_path(history_root: Path) -> Path:
    """Return a collision-safe path for an offline-release backup."""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = history_root / stamp
    suffix = 1
    while candidate.exists():
        candidate = history_root / f"{stamp}-{suffix}"
        suffix += 1
    return candidate


def verify_release(release_root: Path) -> dict:
    for required in ("MANIFEST.json", "SOURCE_LOCK.json", "SHA256SUMS.txt", "VALIDATION_REPORT.json"):
        if not (release_root / required).is_file():
            raise SystemExit(f"missing release evidence: {required}")

    manifest = json.loads((release_root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("apiVersion") != "dw.superapps.distribution/v1":
        raise SystemExit("unsupported release apiVersion")

    for line in (release_root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(None, 1)
        path = release_root / rel
        if not path.is_file():
            raise SystemExit(f"checksum target missing: {rel}")
        actual = sha256_file(path)
        if actual != expected:
            raise SystemExit(f"checksum mismatch: {rel}")

    for component in manifest["spec"]["components"]:
        package = release_root / component["package"]
        if sha256_file(package) != component["sha256"]:
            raise SystemExit(f"component checksum mismatch: {component['name']}")
        with zipfile.ZipFile(package) as archive:
            require_safe_archive(archive)
    return manifest


def install_component(package: Path, destination: Path, force: bool) -> str:
    changed = "installed"
    if destination.exists():
        if not force:
            raise SystemExit(f"target package exists; use --force after review: {destination}")
        shutil.rmtree(destination)
        changed = "replaced"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        require_safe_archive(archive)
        archive.extractall(destination)
    return changed


def install_release(args: argparse.Namespace) -> dict:
    release_root = Path(args.release).resolve()
    workspace = Path(args.workspace).resolve()
    store_root = workspace / ".dw" / "powers"
    history_root = workspace / ".dw" / "history" / "offline-releases"
    bindings_root = workspace / ".dw" / "bindings" / "offline-releases"
    store_root.mkdir(parents=True, exist_ok=True)
    history_root.mkdir(parents=True, exist_ok=True)
    bindings_root.mkdir(parents=True, exist_ok=True)

    manifest = verify_release(release_root)
    backup_root = next_history_path(history_root)
    backup_root.mkdir(parents=True, exist_ok=False)

    if store_root.exists():
        shutil.copytree(store_root, backup_root / "powers", dirs_exist_ok=True)

    installed = []
    for component in manifest["spec"]["components"]:
        name = component["name"]
        package = release_root / component["package"]
        dest = store_root / name
        action = install_component(package, dest, args.force)
        installed.append({"name": name, "action": action, "destination": str(dest)})

    binding = {
        "installedAt": datetime.now(timezone.utc).isoformat(),
        "version": manifest["metadata"]["version"],
        "release": str(release_root),
        "backup": str(backup_root),
        "components": installed,
        "runtimeRootsPreserved": [".gwc", ".ua", ".task-me", ".bmad"],
    }
    (bindings_root / f"{manifest['metadata']['version']}.json").write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": "INSTALL_OK", "backup": str(backup_root), "components": installed}, indent=2))
    return binding


def rollback(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).resolve()
    history_root = workspace / ".dw" / "history" / "offline-releases"
    candidates = sorted([p for p in history_root.iterdir() if p.is_dir()], reverse=True)
    if not candidates:
        raise SystemExit("no rollback history")
    latest = candidates[0] / "powers"
    if not latest.is_dir():
        raise SystemExit(f"rollback snapshot missing powers: {latest}")
    store_root = workspace / ".dw" / "powers"
    if store_root.exists():
        shutil.rmtree(store_root)
    shutil.copytree(latest, store_root)
    print(json.dumps({"result": "ROLLBACK_OK", "restoredFrom": str(latest)}, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or rollback offline release assets.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--release", required=True)

    install = sub.add_parser("install")
    install.add_argument("--release", required=True)
    install.add_argument("--workspace", required=True)
    install.add_argument("--force", action="store_true")

    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--workspace", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "verify":
        verify_release(Path(args.release).resolve())
        print(json.dumps({"result": "VERIFY_OK"}, indent=2))
    elif args.cmd == "install":
        install_release(args)
    elif args.cmd == "rollback":
        rollback(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
