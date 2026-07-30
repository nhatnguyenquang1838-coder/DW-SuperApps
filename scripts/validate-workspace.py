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

from dw_project_registry import ProjectRegistryError, validate_registry
from dw_power_store.common import ConsumerError
from dw_power_store.compatibility import validate_lock

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace.yaml"
SCHEMA = ROOT / "schemas" / "power-manifest.schema.json"
COMPATIBILITY_LOCK = ROOT / "manifests" / "power-compatibility-lock.json"
COMPATIBILITY_SCHEMA = ROOT / "schemas" / "power-compatibility-lock.schema.json"
MANIFEST_DIR = ROOT / "manifests" / "powers"
GITMODULES = ROOT / ".gitmodules"
SUPPORTED_HOSTS = {"kiro", "codex", "copilot", "cline", "kilo", "claude", "custom"}
TARGET_ROLES = {"product", "system"}
DISTRIBUTION_ROOTS = {
    "storeRoot": ".dw/powers",
    "inboxRoot": ".dw/inbox/powers",
    "cacheRoot": ".dw/cache",
    "historyRoot": ".dw/history/powers",
    "bindingsRoot": ".dw/bindings",
    "hostAdaptersRoot": ".",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        fail(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip() if result.returncode == 0 else ""


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return data


def resolve_workspace_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def target_projects(projects: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [project for project in projects.values() if TARGET_ROLES & set(project.get("roles", []))]


def enabled_powers(project: dict[str, Any]) -> list[str]:
    powers = project.get("powers") or {}
    if not isinstance(powers, dict):
        fail(f"project {project['id']} powers must be a mapping")
    enabled = powers.get("enabled") or []
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        fail(f"project {project['id']} powers.enabled must be a string list")
    return enabled


def validate_distribution(workspace: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Path]:
    distribution = workspace.get("distribution")
    if not isinstance(distribution, dict):
        fail("workspace distribution must be a mapping")
    if distribution.get("ownership") != "workspace":
        fail("workspace distribution.ownership must be workspace")
    resolved: dict[str, Path] = {}
    for name, default in DISTRIBUTION_ROOTS.items():
        value = distribution.get(name, default)
        if not isinstance(value, str) or not value.strip():
            fail(f"workspace distribution.{name} must be a path string")
        path = resolve_workspace_path(value)
        if not is_within(path, ROOT.resolve()):
            fail(f"workspace distribution.{name} escapes DW-SuperApps: {path}")
        resolved[name] = path
    if resolved["storeRoot"] == ROOT.resolve():
        fail("workspace distribution.storeRoot cannot be the workspace root")
    if resolved["hostAdaptersRoot"] != ROOT.resolve():
        fail("workspace distribution.hostAdaptersRoot must resolve to DW-SuperApps root")
    for project in targets:
        target_path = resolve_workspace_path(project["path"])
        for name, path in resolved.items():
            if name != "hostAdaptersRoot" and (path == target_path or is_within(path, target_path)):
                fail(f"workspace distribution.{name} resolves inside project {project['id']}: {path}")
    return resolved


def validate_providers(workspace: dict[str, Any]) -> list[dict[str, Any]]:
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


def gitmodule_map() -> dict[str, str]:
    if not GITMODULES.is_file():
        return {}
    paths_output = git("config", "-f", str(GITMODULES), "--get-regexp", r"^submodule\..*\.path$", check=False)
    result: dict[str, str] = {}
    for line in paths_output.splitlines():
        key, path = line.split(maxsplit=1)
        name = key[len("submodule.") : -len(".path")]
        result[path] = git("config", "-f", str(GITMODULES), "--get", f"submodule.{name}.url", check=False)
    return result


def source_fallback_required(manifest: dict[str, Any]) -> bool:
    distribution = manifest.get("spec", {}).get("distribution") or {}
    provider = distribution.get("providerState") or {}
    return provider.get("status") != "published"


def main() -> int:
    workspace = load_yaml(WORKSPACE)
    if "systems" in workspace:
        fail("workspace systems registry is removed; configure Powers and orchestration under projects[]")
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
    if not isinstance(power_entries, list) or not all(isinstance(item, dict) for item in power_entries):
        fail("workspace power entries must be mappings")

    configured_submodules = gitmodule_map()
    try:
        projects = validate_registry(
            workspace,
            root=ROOT,
            gitmodules=configured_submodules if configured_submodules else None,
        )
    except ProjectRegistryError as exc:
        fail(str(exc))

    targets = target_projects(projects)
    distribution = validate_distribution(workspace, targets)

    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        manifest = load_yaml(path)
        errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
        if errors:
            for error in errors:
                location = ".".join(str(part) for part in error.path) or "<root>"
                print(f"ERROR: {path.relative_to(ROOT)}:{location}: {error.message}", file=sys.stderr)
            return 1
        power_id = manifest["metadata"]["id"]
        if power_id in manifests:
            fail(f"duplicate Power manifest id: {power_id}")
        missing_hosts = set(workspace_hosts) - set(manifest["spec"]["hosts"])
        if missing_hosts:
            fail(f"Power {power_id} does not support workspace hosts: {sorted(missing_hosts)}")
        manifests[power_id] = manifest

    compatibility_data = json.loads(COMPATIBILITY_LOCK.read_text(encoding="utf-8"))
    compatibility_schema = json.loads(COMPATIBILITY_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(compatibility_schema).iter_errors(compatibility_data), key=lambda error: list(error.path))
    if errors:
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            print(f"ERROR: {COMPATIBILITY_LOCK.relative_to(ROOT)}:{location}: {error.message}", file=sys.stderr)
        return 1
    try:
        compatibility = validate_lock(manifests)
    except ConsumerError as exc:
        fail(str(exc))

    power_ids = {entry["id"] for entry in power_entries}
    unknown_powers = power_ids - set(manifests)
    if unknown_powers:
        fail(f"workspace references missing Power manifests: {sorted(unknown_powers)}")

    expected_paths = {
        project["path"] for project in projects.values() if project.get("sourceMode") != "offline-local"
    }
    submodule_paths = set(configured_submodules)
    if expected_paths != submodule_paths:
        fail(
            "workspace project paths do not match .gitmodules: "
            f"workspace={sorted(expected_paths)} gitmodules={sorted(submodule_paths)}"
        )

    for entry in power_entries:
        current = manifests[entry["id"]]
        project_id = entry.get("project")
        if not project_id:
            fail(f"Power {entry.get('id')} must reference a project")
        project = projects[str(project_id)]
        if current["spec"]["path"] != project["path"]:
            fail(f"Power path mismatch for {entry['id']}")
        if current["spec"]["source"] != project["source"]:
            fail(f"Power source mismatch for {entry['id']}")

    external_ids = set(manifests) - power_ids
    enabled_power_ids = {power_id for project in targets for power_id in enabled_powers(project)}
    for power_id in sorted(external_ids & enabled_power_ids):
        source_path = ROOT / manifests[power_id]["spec"]["path"]
        package_manifest = distribution["storeRoot"] / power_id / "MANIFEST.json"
        if not source_path.exists() and not package_manifest.is_file() and source_fallback_required(manifests[power_id]):
            fail(f"external Power {power_id} local routing path is missing: {source_path.relative_to(ROOT)}")

    runtime_roots = (workspace.get("data_ownership") or {}).get("roots", {})
    if (workspace.get("data_ownership") or {}).get("policy") != "project-owned":
        fail("workspace data_ownership.policy must be project-owned")
    for project in targets:
        unknown = set(enabled_powers(project)) - set(manifests)
        if unknown:
            fail(f"project {project['id']} enables unknown Powers: {sorted(unknown)}")
        target_root = resolve_workspace_path(project["path"])
        for runtime_name in runtime_roots.values():
            runtime = (target_root / str(runtime_name)).resolve()
            if not is_within(runtime, target_root):
                fail(f"unsafe runtime root for project {project['id']}: {runtime}")

    print(
        f"PASS: {len(projects)} projects, {len(manifests)} Powers "
        f"({len(power_entries)} source-project, {len(external_ids)} package-only), "
        f"{len(targets)} runtime targets, {len(workspace_hosts)} hosts, {len(providers)} providers, "
        f"{len(submodule_paths)} submodules, store={distribution['storeRoot'].relative_to(ROOT)}, "
        f"compatibility={compatibility['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
