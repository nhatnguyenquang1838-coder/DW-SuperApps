#!/usr/bin/env python3
"""Build all Power distributions from source submodules and stage them."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POWER_MANIFESTS = ROOT / "manifests" / "powers"
POWER_SOURCES = {
    "gwc": ROOT / "projects" / "gwc",
    "task-me": ROOT / "projects" / "task-me",
    "bmad": ROOT / "projects" / "bmad",
    "ua": ROOT / "projects" / "ua",
}
DEFAULT_OUTPUT = ROOT / ".dw" / "distributions"
DEFAULT_STAGING = ROOT / ".kilo" / "staging" / "power-dist"
FOUNDATION_REF_ENV = "DW_FOUNDATION_REF"


def load_manifest(power_id: str) -> dict[str, Any]:
    import yaml

    path = POWER_MANIFESTS / f"{power_id}.yaml"
    if not path.is_file():
        raise SystemExit(f"missing power manifest: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_recipe(power_id: str, source_root: Path) -> Path:
    recipe = source_root / "distribution" / "power-package.yaml"
    if not recipe.is_file():
        raise SystemExit(f"missing distribution recipe for {power_id}: {recipe}")
    return recipe


def git_rev_parse(repo: Path, ref: str = "HEAD") -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", ref],
        text=True,
    ).strip()


def git_source_date_epoch(repo: Path, ref: str = "HEAD") -> int:
    return int(
        subprocess.check_output(
            ["git", "-C", str(repo), "show", "-s", "--format=%ct", ref],
            text=True,
        ).strip()
    )


def build_power(
    power_id: str,
    source_root: Path,
    output_root: Path,
    foundation_ref: str,
) -> dict[str, Any]:
    recipe_path = resolve_recipe(power_id, source_root)
    source_sha = git_rev_parse(source_root)
    source_epoch = git_source_date_epoch(source_root)
    version = f"main-{source_sha[:12]}"
    build_script = ROOT / "scripts" / "power_dist_capability.py"
    if not build_script.is_file():
        raise SystemExit(f"missing builder script: {build_script}")

    cmd = [
        sys.executable,
        str(build_script),
        "build",
        "--recipe",
        str(recipe_path),
        "--source",
        str(source_root),
        "--output",
        str(output_root),
        "--version",
        version,
        "--source-repository",
        f"nhatnguyenquang1838-coder/{power_id}",
        "--source-ref",
        "main",
        "--source-sha",
        source_sha,
        "--source-date-epoch",
        str(source_epoch),
        "--templates-root",
        str(ROOT / "templates" / "power-runtime"),
    ]
    subprocess.run(cmd, check=True, text=True)

    staging_root = output_root / "staging" / f"{power_id}-{version}"
    archive = output_root / "assets" / f"{power_id}-{version}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    return {
        "power_id": power_id,
        "version": version,
        "source_sha": source_sha,
        "source_epoch": source_epoch,
        "staging_root": str(staging_root),
        "archive": str(archive),
        "checksum": str(checksum),
        "recipe": str(recipe_path),
    }


def build_all(
    output_root: Path,
    staging_root: Path,
    foundation_ref: str,
    powers: list[str] | None = None,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "foundation_ref": foundation_ref,
        "powers": {},
    }
    selected = powers or list(POWER_SOURCES.keys())
    for power_id in selected:
        if power_id not in POWER_SOURCES:
            raise SystemExit(f"unknown power: {power_id}")
        print(f"[builder] building {power_id}...", flush=True)
        result = build_power(power_id, POWER_SOURCES[power_id], output_root, foundation_ref)
        results["powers"][power_id] = result
        print(f"[builder] built {power_id}: {result['archive']}", flush=True)

    staging_root.mkdir(parents=True, exist_ok=True)
    for power_id, result in results["powers"].items():
        dest = staging_root / f"{power_id}-{result['version']}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(Path(result["staging_root"]), dest)
        shutil.copy2(result["archive"], staging_root / f"{power_id}-{result['version']}.zip")
        shutil.copy2(result["checksum"], staging_root / f"{power_id}-{result['version']}.zip.sha256")

    summary = staging_root / "build-summary.json"
    summary.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[builder] staging summary: {summary}", flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build all Power distributions.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--staging", default=str(DEFAULT_STAGING))
    parser.add_argument("--foundation-ref", default=os.environ.get(FOUNDATION_REF_ENV) or git_rev_parse(ROOT))
    parser.add_argument("--power", action="append", dest="powers")
    args = parser.parse_args(argv)

    results = build_all(
        Path(args.output).resolve(),
        Path(args.staging).resolve(),
        args.foundation_ref,
        args.powers,
    )
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
