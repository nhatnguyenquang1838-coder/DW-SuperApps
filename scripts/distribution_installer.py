#!/usr/bin/env python3
"""Install Power distributions from local package roots and validate them."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = ROOT / ".kilo" / "staging" / "power-dist"


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    print(f"[installer] running: {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def install_power(package_root: Path, store_root: Path, target: Path, power_id: str) -> dict[str, Any]:
    runtime = package_root / "lib" / "power_runtime.py"
    if not runtime.is_file():
        raise SystemExit(f"missing power runtime: {runtime}")

    store_root.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(runtime),
        "install",
        "--store-root",
        str(store_root),
        "--target",
        str(target),
    ]
    completed = run(cmd, capture_output=True)
    return json.loads(completed.stdout)


def doctor_power(package_root: Path, store_root: Path, target: Path, power_id: str) -> dict[str, Any]:
    runtime = package_root / "lib" / "power_runtime.py"
    cmd = [
        sys.executable,
        str(runtime),
        "doctor",
        "--store-root",
        str(store_root),
        "--target",
        str(target),
    ]
    completed = run(cmd, capture_output=True)
    return json.loads(completed.stdout)


def uninstall_power(package_root: Path, store_root: Path, target: Path, power_id: str) -> dict[str, Any]:
    runtime = package_root / "lib" / "power_runtime.py"
    cmd = [
        sys.executable,
        str(runtime),
        "uninstall",
        "--store-root",
        str(store_root),
        "--target",
        str(target),
    ]
    completed = run(cmd, capture_output=True)
    return json.loads(completed.stdout)


def verify_package(package_root: Path, power_id: str) -> dict[str, Any]:
    builder = ROOT / "scripts" / "power_dist.py"
    cmd = [sys.executable, str(builder), "verify", "--package-root", str(package_root)]
    run(cmd)
    manifest_path = package_root / "MANIFEST.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def validate_power(
    power_id: str,
    package_root: Path,
    store_root: Path,
    target: Path,
) -> dict[str, Any]:
    print(f"[installer] validating {power_id}...", flush=True)
    manifest = verify_package(package_root, power_id)
    install_json = install_power(package_root, store_root, target, power_id)
    doctor_json = doctor_power(package_root, store_root, target, power_id)
    uninstall_json = uninstall_power(package_root, store_root, target, power_id)

    runtime_root_name = manifest.get("spec", {}).get("runtimeDataRoot", f".{power_id}")
    runtime_root = target / runtime_root_name
    return {
        "power_id": power_id,
        "status": "PASS",
        "manifest": manifest,
        "install": install_json,
        "doctor": doctor_json,
        "uninstall": uninstall_json,
        "runtime_data_preserved": runtime_root.is_dir(),
        "store_path": str((store_root / power_id).resolve()),
        "target_path": str(target.resolve()),
    }


def validate_staging(
    staging_root: Path,
    store_root: Path,
    target: Path,
    powers: list[str] | None = None,
) -> dict[str, Any]:
    if not staging_root.is_dir():
        raise SystemExit(f"staging root missing: {staging_root}")

    selected = powers or [
        p.name.split("-")[0] for p in sorted(staging_root.glob("*-*")) if p.is_dir()
    ]
    results: dict[str, Any] = {
        "validated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "staging_root": str(staging_root),
        "store_root": str(store_root),
        "target_root": str(target),
        "powers": {},
    }
    for power_id in selected:
        candidates = sorted(staging_root.glob(f"{power_id}-*"))
        if not candidates:
            raise SystemExit(f"missing staged package for {power_id} under {staging_root}")
        package_root = candidates[0]
        results["powers"][power_id] = validate_power(power_id, package_root, store_root, target)

    report = staging_root / "validation-report.json"
    report.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[installer] validation report: {report}", flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate staged Power distributions.")
    parser.add_argument("--staging", default=str(DEFAULT_STAGING))
    parser.add_argument("--store-root")
    parser.add_argument("--target")
    parser.add_argument("--power", action="append", dest="powers")
    args = parser.parse_args(argv)

    staging = Path(args.staging).resolve()
    store = Path(args.store_root).resolve() if args.store_root else staging / ".store"
    target = Path(args.target).resolve() if args.target else staging / ".consumer"

    results = validate_staging(staging, store, target, args.powers)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
