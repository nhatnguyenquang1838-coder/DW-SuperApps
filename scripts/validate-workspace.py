#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as exc:
    print(
        "Missing validation dependencies. Run: python -m pip install -r requirements-dev.txt",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace.yaml"
SCHEMA = ROOT / "schemas" / "power-manifest.schema.json"
MANIFEST_DIR = ROOT / "manifests" / "powers"
GITMODULES = ROOT / ".gitmodules"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return data


def validate_entrypoints(power_id: str, manifest: dict[str, Any]) -> None:
    power_root = ROOT / manifest["spec"]["path"]
    if not power_root.exists():
        fail(f"Power submodule is not initialized: {manifest['spec']['path']}")
    candidates = manifest["spec"]["entrypoints"]["skillCandidates"]
    if not any((power_root / candidate).is_file() for candidate in candidates):
        rendered = ", ".join(candidates)
        fail(f"Power {power_id} has no existing skill entrypoint; checked: {rendered}")


def main() -> int:
    workspace = load_yaml(WORKSPACE)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    if workspace.get("apiVersion") != "ai-workspace/v1" or workspace.get("kind") != "Workspace":
        fail("workspace.yaml must use apiVersion ai-workspace/v1 and kind Workspace")

    workspace_hosts = set(workspace.get("hosts") or [])
    if not workspace_hosts:
        fail("workspace.yaml must register at least one host")
    unknown_hosts = workspace_hosts - {"kiro", "codex"}
    if unknown_hosts:
        fail(f"workspace.yaml registers unsupported hosts: {sorted(unknown_hosts)}")

    power_entries = workspace.get("powers") or []
    system_entries = workspace.get("systems") or []
    if not power_entries or not system_entries:
        fail("workspace.yaml must register at least one Power and one system")

    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        manifest = load_yaml(path)
        errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
        if errors:
            for error in errors:
                location = ".".join(str(part) for part in error.path) or "<root>"
                print(
                    f"ERROR: {path.relative_to(ROOT)}:{location}: {error.message}",
                    file=sys.stderr,
                )
            return 1
        power_id = manifest["metadata"]["id"]
        if power_id in manifests:
            fail(f"duplicate Power manifest id: {power_id}")
        manifests[power_id] = manifest

    workspace_power_ids = {entry["id"] for entry in power_entries}
    if workspace_power_ids != set(manifests):
        fail(
            "workspace Power IDs do not match manifests: "
            f"workspace={sorted(workspace_power_ids)} manifests={sorted(manifests)}"
        )

    configured_paths = set(
        filter(
            None,
            git(
                "config",
                "-f",
                str(GITMODULES),
                "--get-regexp",
                r"^submodule\..*\.path$",
            ).splitlines(),
        )
    )
    submodule_paths = {line.split(maxsplit=1)[1] for line in configured_paths}

    expected_paths = {entry["path"] for entry in power_entries} | {
        entry["path"] for entry in system_entries
    }
    if expected_paths != submodule_paths:
        fail(
            "workspace paths do not match .gitmodules: "
            f"workspace={sorted(expected_paths)} gitmodules={sorted(submodule_paths)}"
        )

    ownership_roots = set((workspace.get("data_ownership") or {}).get("roots", {}).values())

    for entry in power_entries:
        power_id = entry["id"]
        manifest = manifests[power_id]
        spec = manifest["spec"]
        if spec["path"] != entry["path"]:
            fail(f"Power path mismatch for {power_id}")
        if spec["source"] != entry["source"]:
            fail(f"Power source mismatch for {power_id}")
        unsupported = set(spec["hosts"]) - (workspace_hosts | {"cli"})
        if unsupported:
            fail(
                f"Power {power_id} declares hosts not supported by workspace: "
                f"{sorted(unsupported)}"
            )
        if spec["runtimeDataRoot"] not in ownership_roots:
            fail(
                f"Power {power_id} runtimeDataRoot {spec['runtimeDataRoot']} "
                "is not registered by workspace data_ownership"
            )
        expected_write = f"{spec['runtimeDataRoot']}/**"
        if expected_write not in spec["permissions"]["write"]:
            fail(f"Power {power_id} must declare write permission {expected_write}")
        validate_entrypoints(power_id, manifest)

    for system in system_entries:
        unknown = set(system.get("enabled_powers") or []) - workspace_power_ids
        if unknown:
            fail(f"system {system['id']} enables unknown Powers: {sorted(unknown)}")
        system_path = ROOT / system["path"]
        if not system_path.exists():
            fail(f"system submodule is not initialized: {system['path']}")

    print(
        f"PASS: {len(power_entries)} Powers, {len(system_entries)} systems, "
        f"{len(submodule_paths)} submodules, {len(workspace_hosts)} hosts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
