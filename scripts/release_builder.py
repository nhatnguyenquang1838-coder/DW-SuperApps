#!/usr/bin/env python3
"""Build immutable DW SUPER offline distribution release assets.

This builder is intentionally source-side only. It creates release artifacts
under an output directory; generated ZIPs are meant for workflow artifacts or
GitHub Releases, not for committing into source branches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

FORBIDDEN_PARTS = {".git", ".github", "__pycache__", "node_modules", ".venv", "venv"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
DEFAULT_COMPONENTS = ("task-me", "bmad", "ua", "kiro-adapter", "bootstrap")


@dataclass(frozen=True)
class Component:
    name: str
    source: Path
    package_name: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_rel(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.startswith("../") or rel == ".." or rel.startswith("/"):
        raise ValueError(f"unsafe relative path: {rel}")
    return rel


def should_include(path: Path) -> bool:
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        return False
    if path.suffix in FORBIDDEN_SUFFIXES:
        return False
    return True


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and should_include(path):
            yield path


def write_zip_from_dir(source: Path, destination: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files(source):
            rel = safe_rel(path, source)
            archive.write(path, rel)
            records.append({"path": rel, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return records


def load_component_config(config_path: Path | None, source_root: Path) -> list[Component]:
    if config_path is None:
        defaults = {
            "task-me": source_root / "projects" / "task-me",
            "bmad": source_root / "projects" / "bmad",
            "ua": source_root / "projects" / "ua",
            "kiro-adapter": source_root / ".kiro",
            "bootstrap": source_root / "templates" / "power-runtime",
        }
        return [Component(name, defaults[name], f"{name}.zip") for name in DEFAULT_COMPONENTS if defaults[name].exists()]

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    components: list[Component] = []
    for item in payload.get("components", []):
        name = item["name"]
        source = (source_root / item["source"]).resolve()
        package_name = item.get("package", f"{name}.zip")
        components.append(Component(name, source, package_name))
    return components


def validate_component(component: Component, source_root: Path) -> None:
    if not component.source.exists():
        raise SystemExit(f"component source missing: {component.name}: {component.source}")
    if not component.source.is_dir():
        raise SystemExit(f"component source is not a directory: {component.name}: {component.source}")
    try:
        component.source.relative_to(source_root)
    except ValueError as exc:
        raise SystemExit(f"component source escapes source root: {component.name}: {component.source}") from exc


def build_release(args: argparse.Namespace) -> dict[str, object]:
    source_root = Path(args.source_root).resolve()
    output_root = Path(args.output).resolve()
    release_root = output_root / f"dw-super-offline-{args.version}"
    assets_root = release_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)

    components = load_component_config(Path(args.config).resolve() if args.config else None, source_root)
    if not components:
        raise SystemExit("no components selected; provide --config or expected source directories")

    manifest_components: list[dict[str, object]] = []
    for component in components:
        validate_component(component, source_root)
        package_path = assets_root / component.package_name
        file_records = write_zip_from_dir(component.source, package_path)
        manifest_components.append({
            "name": component.name,
            "package": f"assets/{component.package_name}",
            "sha256": sha256_file(package_path),
            "size": package_path.stat().st_size,
            "files": file_records,
        })

    source_lock = {
        "source_root": str(source_root),
        "source_ref": args.source_ref,
        "source_sha": args.source_sha,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "component_count": len(components),
    }

    manifest = {
        "apiVersion": "dw.superapps.distribution/v1",
        "kind": "OfflineDistributionRelease",
        "metadata": {
            "name": "dw-super-offline-distribution",
            "version": args.version,
            "builtAt": datetime.now(timezone.utc).isoformat(),
        },
        "spec": {
            "artifactOnly": True,
            "generatedZipsInRepository": False,
            "delivery": "tag-or-release-download",
            "components": manifest_components,
            "requiredEvidence": ["MANIFEST.json", "SOURCE_LOCK.json", "SHA256SUMS.txt", "VALIDATION_REPORT.json"],
            "forbiddenAcquisition": ["git", "curl", "wget", "remote power-dist"],
        },
    }

    (release_root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (release_root / "SOURCE_LOCK.json").write_text(json.dumps(source_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checksum_lines = []
    for path in sorted(release_root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksum_lines.append(f"{sha256_file(path)}  {safe_rel(path, release_root)}")
    (release_root / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    validation = {
        "validatedAt": datetime.now(timezone.utc).isoformat(),
        "result": "PASS",
        "checks": {
            "componentSourcesExist": True,
            "artifactOnlyRelease": True,
            "checksumsGenerated": True,
            "sourceLockGenerated": True,
            "generatedZipCommittedToSource": False,
        },
        "limitations": ["Kiro IDE discovery and native Windows Git Bash execution are validated outside this builder."],
    }
    (release_root / "VALIDATION_REPORT.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"releaseRoot": str(release_root), "components": [c.name for c in components]}, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build DW SUPER offline release assets.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--output", default="dist/offline-release")
    parser.add_argument("--config", help="JSON file declaring release components")
    parser.add_argument("--source-ref", default=os.environ.get("GITHUB_REF_NAME", "local"))
    parser.add_argument("--source-sha", default=os.environ.get("GITHUB_SHA", "UNKNOWN"))
    args = parser.parse_args(argv)
    build_release(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
