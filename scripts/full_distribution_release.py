#!/usr/bin/env python3
"""Assemble a full DW-SuperApps release from validated Power packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from power_dist import verify_package


DEFAULT_POWERS = ("gwc", "ua", "task-me", "bmad")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_deterministic_bundle(source_root: Path, destination: Path, source_date_epoch: int) -> None:
    timestamp = max(source_date_epoch, 315532800)
    date_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).timetuple()[:6]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.name == destination.name:
                continue
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=date_time)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(destination)


def write_checksums(release_root: Path, *, include_bundle: bool) -> None:
    checksum_lines = []
    bundle_name = next((path.name for path in release_root.glob("dw-superapps-full-*.zip")), None)
    for path in sorted(release_root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        if not include_bundle and bundle_name and path.name == bundle_name:
            continue
        checksum_lines.append(f"{sha256_file(path)}  {path.relative_to(release_root).as_posix()}")
    (release_root / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def package_paths(distribution_root: Path, power_id: str) -> tuple[Path, Path, Path]:
    staging_root = distribution_root / "staging"
    candidates = sorted(path for path in staging_root.glob(f"{power_id}-*") if path.is_dir())
    if len(candidates) != 1:
        raise SystemExit(f"expected exactly one staged package for {power_id}, found {len(candidates)}")
    package_root = candidates[0]
    archive = distribution_root / "assets" / f"{package_root.name}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    if not archive.is_file() or not checksum.is_file():
        raise SystemExit(f"missing package asset pair for {power_id}: {archive}")
    return package_root, archive, checksum


def assemble(args: argparse.Namespace) -> dict:
    distribution_root = Path(args.distribution_root).resolve()
    output_root = Path(args.output).resolve()
    release_root = output_root / f"dw-superapps-full-{args.version}"
    if release_root.exists():
        shutil.rmtree(release_root)
    assets_root = release_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)

    components = []
    source_packages = []
    for power_id in args.powers:
        package_root, archive, checksum = package_paths(distribution_root, power_id)
        package_manifest = verify_package(package_root)
        actual_sha = sha256_file(archive)
        checksum_text = checksum.read_text(encoding="utf-8").split()[0]
        if checksum_text != actual_sha:
            raise SystemExit(f"package checksum mismatch for {power_id}")

        shutil.copy2(archive, assets_root / archive.name)
        shutil.copy2(checksum, assets_root / checksum.name)
        components.append({
            "name": power_id,
            "package": f"assets/{archive.name}",
            "sha256": actual_sha,
            "size": archive.stat().st_size,
            "packageVersion": package_manifest["metadata"]["version"],
            "source": package_manifest["metadata"],
        })
        source_packages.append(package_manifest["metadata"])

    validation_path = distribution_root / "validation-report.json"
    if not validation_path.is_file():
        raise SystemExit(f"missing validation report: {validation_path}")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    power_results = validation.get("powers", {})
    missing = [power_id for power_id in args.powers if power_id not in power_results]
    failed = [power_id for power_id in args.powers if power_results.get(power_id, {}).get("status") != "PASS"]
    if missing or failed:
        raise SystemExit(f"validation report is incomplete: missing={missing}, failed={failed}")

    manifest = {
        "apiVersion": "dw.superapps.distribution/v1",
        "kind": "OfflineDistributionRelease",
        "metadata": {
            "name": "dw-superapps-full-distribution",
            "version": args.version,
        },
        "spec": {
            "artifactOnly": True,
            "generatedZipsInRepository": False,
            "delivery": "tag-or-release-download",
            "components": components,
            "requiredEvidence": ["MANIFEST.json", "SOURCE_LOCK.json", "SHA256SUMS.txt", "VALIDATION_REPORT.json"],
            "powers": list(args.powers),
        },
    }
    source_lock = {
        "apiVersion": "dw.superapps.distribution/v1",
        "sourceRef": args.source_ref,
        "sourceSha": args.source_sha,
        "sourceDateEpoch": args.source_date_epoch,
        "powers": source_packages,
    }
    full_validation = {
        "apiVersion": "dw.superapps.distribution/v1",
        "result": "PASS",
        "releaseVersion": args.version,
        "sourceSha": args.source_sha,
        "checks": {
            "allPowerPackagesVerified": True,
            "allArchiveChecksumsVerified": True,
            "offlineInstallerValidation": True,
        },
        "powers": power_results,
    }

    write_json(release_root / "MANIFEST.json", manifest)
    write_json(release_root / "SOURCE_LOCK.json", source_lock)
    write_json(release_root / "VALIDATION_REPORT.json", full_validation)

    bundle = release_root / f"dw-superapps-full-{args.version}.zip"
    write_checksums(release_root, include_bundle=False)
    write_deterministic_bundle(release_root, bundle, args.source_date_epoch)
    write_checksums(release_root, include_bundle=True)

    result = {
        "releaseRoot": str(release_root),
        "bundle": str(bundle),
        "version": args.version,
        "powers": list(args.powers),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble a full DW-SuperApps release from validated Power packages.")
    parser.add_argument("--distribution-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--power", action="append", dest="powers", choices=DEFAULT_POWERS)
    args = parser.parse_args(argv)
    args.powers = args.powers or list(DEFAULT_POWERS)
    assemble(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
