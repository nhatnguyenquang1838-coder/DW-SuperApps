#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
SUPPORTED_HOSTS = {
    "kiro",
    "codex",
    "copilot",
    "cline",
    "kilo",
    "claude",
    "custom",
}


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


def load_yaml(path: Path) -> dict:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return data


def validate_providers(workspace: dict) -> list[dict]:
    providers = workspace.get("providers") or []
    if not isinstance(providers, list):
        fail("workspace providers must be a list")
    seen: set[str] = set()
    for provider in providers:
        if not isinstance(provider, dict):
            fail("workspace provider entries must be mappings")
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            fail("workspace provider entry requires id")
        if provider_id in seen:
            fail(f"duplicate provider id: {provider_id}")
        seen.add(provider_id)
        if provider.get("type") != "openai-compatible":
            fail(f"provider {provider_id} must use type openai-compatible")
        base_url = provider.get("base_url")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            fail(f"provider {provider_id} requires an HTTP base_url")
        if not provider.get("model_env") and not provider.get("default_model"):
            fail(f"provider {provider_id} requires model_env or default_model")
    return providers


def main() -> int:
    workspace = load_yaml(WORKSPACE)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    if workspace.get("apiVersion") != "ai-workspace/v1" or workspace.get("kind") != "Workspace":
        fail("workspace.yaml must use apiVersion ai-workspace/v1 and kind Workspace")

    workspace_hosts = workspace.get("hosts") or []
    if not isinstance(workspace_hosts, list) or not workspace_hosts:
        fail("workspace.yaml must register at least one host")
    unknown_hosts = set(workspace_hosts) - SUPPORTED_HOSTS
    if unknown_hosts:
        fail(f"workspace registers unsupported hosts: {sorted(unknown_hosts)}")
    if len(workspace_hosts) != len(set(workspace_hosts)):
        fail("workspace hosts must be unique")

    providers = validate_providers(workspace)
    power_entries = workspace.get("powers") or []
    system_entries = workspace.get("systems") or []
    if not power_entries or not system_entries:
        fail("workspace.yaml must register at least one Power and one system")

    manifests: dict[str, dict] = {}
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
        missing_hosts = set(workspace_hosts) - set(manifest["spec"]["hosts"])
        if missing_hosts:
            fail(f"Power {power_id} does not support workspace hosts: {sorted(missing_hosts)}")
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

    for entry in power_entries:
        manifest = manifests[entry["id"]]
        if manifest["spec"]["path"] != entry["path"]:
            fail(f"Power path mismatch for {entry['id']}")
        if manifest["spec"]["source"] != entry["source"]:
            fail(f"Power source mismatch for {entry['id']}")

    for system in system_entries:
        unknown = set(system.get("enabled_powers") or []) - workspace_power_ids
        if unknown:
            fail(f"system {system['id']} enables unknown Powers: {sorted(unknown)}")

    print(
        f"PASS: {len(power_entries)} Powers, {len(system_entries)} systems, "
        f"{len(workspace_hosts)} hosts, {len(providers)} providers, "
        f"{len(submodule_paths)} submodules"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
