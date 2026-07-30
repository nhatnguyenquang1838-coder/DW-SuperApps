#!/usr/bin/env python3
"""Verify and install DW SUPER offline release assets into a workspace store."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # The standalone verifier remains usable without PyYAML.
    yaml = None


PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
DEFAULT_HOSTS = ["kiro", "codex", "copilot", "cline", "kilo", "claude", "custom"]
DEFAULT_RUNTIME_ROOTS = {"ua": ".ua", "task_me": ".task-me", "gwc": ".gwc", "bmad": ".bmad"}
PROJECT_ROLES = {"power-source", "product", "runtime-target", "library", "tooling"}


class SetupError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def safe_relative(root: Path, value: str, *, allow_root: bool = False) -> Path:
    raw = Path(value.replace("\\", "/"))
    if raw.is_absolute() or ".." in raw.parts:
        raise SetupError(f"unsafe relative path: {value}")
    resolved = (root / raw).resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SetupError(f"path escapes root: {value}") from exc
    if not allow_root and str(relative) in {"", "."}:
        raise SetupError(f"path cannot be the workspace root: {value}")
    return relative


def normalize_repository(value: str) -> str:
    result = value.strip()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    if result.endswith(".git"):
        result = result[:-4]
    result = result.strip("/")
    if not REPOSITORY.fullmatch(result):
        raise SetupError(f"project source must use owner/name metadata: {value}")
    return result


def require_yaml() -> Any:
    if yaml is None:
        raise SetupError(
            "BLOCKED_PYTHON_DEPENDENCY: PyYAML is required for workspace registration/repair; "
            "use the release-local runtime/requirements-dev.txt in an offline-capable Python environment"
        )
    return yaml


def load_yaml_file(path: Path) -> dict[str, Any]:
    parser = require_yaml()
    try:
        data = parser.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SetupError(f"workspace YAML is invalid: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupError(f"workspace YAML must be a mapping: {path}")
    return data


def template_workspace(workspace_id: str, workspace_name: str) -> dict[str, Any]:
    return {
        "apiVersion": "ai-workspace/v1",
        "kind": "Workspace",
        "metadata": {"id": workspace_id, "name": workspace_name},
        "hosts": list(DEFAULT_HOSTS),
        "providers": [
            {
                "id": "ollama",
                "type": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "api_key": "ollama",
                "model_env": "OLLAMA_MODEL",
                "default_model": "qwen3-coder:30b",
            }
        ],
        "distribution": {
            "ownership": "workspace",
            "storeRoot": ".dw/powers",
            "inboxRoot": ".dw/inbox/powers",
            "cacheRoot": ".dw/cache",
            "historyRoot": ".dw/history/powers",
            "bindingsRoot": ".dw/bindings",
            "hostAdaptersRoot": ".",
        },
        "projects": [],
        "powers": [],
        "data_ownership": {"policy": "project-owned", "roots": dict(DEFAULT_RUNTIME_ROOTS)},
    }


def render_workspace_template(release_root: Path, workspace_id: str, workspace_name: str) -> str:
    template = release_root / "runtime" / "workspace-template.yaml"
    if template.is_file():
        escaped_name = json.dumps(workspace_name, ensure_ascii=False)[1:-1]
        return template.read_text(encoding="utf-8").replace(
            "__WORKSPACE_ID__", workspace_id
        ).replace("__WORKSPACE_NAME__", escaped_name)
    # Backward-compatible fallback for a pre-bootstrap release.
    if yaml is not None:
        return yaml.safe_dump(template_workspace(workspace_id, workspace_name), sort_keys=False, allow_unicode=True)
    return (
        "apiVersion: ai-workspace/v1\n"
        "kind: Workspace\n"
        "metadata:\n"
        f"  id: {workspace_id}\n"
        f"  name: {json.dumps(workspace_name, ensure_ascii=False)}\n"
        "hosts: [kiro, codex, copilot, cline, kilo, claude, custom]\n"
        "distribution:\n"
        "  ownership: workspace\n"
        "  storeRoot: .dw/powers\n"
        "  inboxRoot: .dw/inbox/powers\n"
        "  cacheRoot: .dw/cache\n"
        "  historyRoot: .dw/history/powers\n"
        "  bindingsRoot: .dw/bindings\n"
        "  hostAdaptersRoot: .\n"
        "projects: []\n"
        "powers: []\n"
        "data_ownership:\n"
        "  policy: project-owned\n"
        "  roots:\n"
        "    ua: .ua\n"
        "    task_me: .task-me\n"
        "    gwc: .gwc\n"
        "    bmad: .bmad\n"
    )


def package_members(archive: zipfile.ZipFile) -> tuple[dict[str, zipfile.ZipInfo], str]:
    require_safe_archive(archive)
    names = [info.filename.replace("\\", "/").rstrip("/") for info in archive.infolist() if info.filename]
    manifest_names = [name for name in names if name == "MANIFEST.json" or name.endswith("/MANIFEST.json")]
    if len(manifest_names) != 1:
        raise SetupError(f"package archive must contain one MANIFEST.json; found {len(manifest_names)}")
    manifest_name = manifest_names[0]
    prefix = manifest_name[: -len("MANIFEST.json")]
    members: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        name = info.filename.replace("\\", "/").rstrip("/")
        if not name:
            continue
        if prefix and name.startswith(prefix):
            name = name[len(prefix) :]
        members[name] = info
    return members, manifest_name


def verify_package_archive(package: Path, expected_power_id: str) -> tuple[dict[str, Any], bytes]:
    with zipfile.ZipFile(package) as archive:
        members, manifest_name = package_members(archive)
        manifest_bytes = archive.read(manifest_name)
        try:
            data = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SetupError(f"package manifest is not valid JSON: {package}") from exc
        if data.get("metadata", {}).get("powerId") != expected_power_id:
            raise SetupError(
                f"package power ID mismatch: expected {expected_power_id}, "
                f"found {data.get('metadata', {}).get('powerId')}"
            )
        runtime = Path(str(data.get("spec", {}).get("runtimeDataRoot", "")))
        if not str(runtime) or runtime.is_absolute() or ".." in runtime.parts:
            raise SetupError(f"package runtimeDataRoot is unsafe: {expected_power_id}")
        for entry in data.get("files", []):
            relative = str(entry.get("path", ""))
            info = members.get(relative)
            if info is None or info.is_dir():
                raise SetupError(f"package file missing: {expected_power_id}/{relative}")
            content = archive.read(info)
            if len(content) != entry.get("size") or sha256_bytes(content) != entry.get("sha256"):
                raise SetupError(f"package file checksum mismatch: {expected_power_id}/{relative}")
        for entrypoint in data.get("spec", {}).get("entrypoints", []):
            info = members.get(str(entrypoint))
            if info is None or info.is_dir():
                raise SetupError(f"package entrypoint missing: {expected_power_id}/{entrypoint}")
        return data, manifest_bytes


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

    required_evidence = manifest.get("spec", {}).get("requiredEvidence", [])
    if not isinstance(required_evidence, list):
        raise SystemExit("release requiredEvidence must be a list")
    for required in required_evidence:
        if not isinstance(required, str) or not required or not (release_root / required).is_file():
            raise SystemExit(f"required release asset missing: {required}")

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

    runtime_manifest_path = release_root / "RUNTIME_MANIFEST.json"
    if runtime_manifest_path.is_file():
        runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
        if runtime_manifest.get("root") != "runtime" or not isinstance(runtime_manifest.get("files"), list):
            raise SystemExit("invalid RUNTIME_MANIFEST.json")
        runtime_root = (release_root / "runtime").resolve()
        for entry in runtime_manifest["files"]:
            relative = str(entry.get("path", ""))
            path = (runtime_root / relative).resolve()
            try:
                path.relative_to(runtime_root)
            except ValueError as exc:
                raise SystemExit(f"runtime manifest path escapes runtime root: {relative}") from exc
            if not path.is_file():
                raise SystemExit(f"runtime manifest file missing: {relative}")
            if path.stat().st_size != entry.get("size") or sha256_file(path) != entry.get("sha256"):
                raise SystemExit(f"runtime manifest checksum mismatch: {relative}")

    for component in manifest["spec"]["components"]:
        package = release_root / component["package"]
        if sha256_file(package) != component["sha256"]:
            raise SystemExit(f"component checksum mismatch: {component['name']}")
        if component.get("packageVersion") or component.get("runtimeDataRoot"):
            package_manifest, _ = verify_package_archive(package, component["name"])
            expected_version = component.get("packageVersion")
            if expected_version and package_manifest.get("metadata", {}).get("version") != expected_version:
                raise SystemExit(f"component version mismatch: {component['name']}")
        else:
            # Keep the older generic offline-release format verifiable. The
            # full distribution format opts into Power package verification
            # through packageVersion/runtimeDataRoot above.
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
        names = [info.filename.replace("\\", "/").rstrip("/") for info in archive.infolist()]
        top_levels = {name.split("/", 1)[0] for name in names if name}
        candidate_root = next(iter(top_levels)) if len(top_levels) == 1 else None
        has_nested_member = bool(candidate_root) and any(
            name.startswith(f"{candidate_root}/") for name in names
        )
        strip_root = candidate_root if has_nested_member else None
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/").rstrip("/")
            if not normalized:
                continue
            parts = normalized.split("/")
            if strip_root and parts[0] == strip_root:
                parts = parts[1:]
            if not parts:
                continue
            target = (destination.joinpath(*parts)).resolve()
            try:
                target.relative_to(destination.resolve())
            except ValueError as exc:
                raise SystemExit(f"archive path escapes install destination: {info.filename}") from exc
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
    return changed


def backup_path(source: Path, backup_root: Path, relative: str) -> Path:
    if source.is_symlink():
        raise SetupError(f"refusing to back up symlink: {source}")
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(source, destination)
    return destination


def install_runtime(release_root: Path, workspace: Path, backup_root: Path, repair: bool) -> dict[str, Any]:
    runtime_manifest_path = release_root / "RUNTIME_MANIFEST.json"
    if not runtime_manifest_path.is_file():
        raise SetupError(
            "BLOCKED_RELEASE_RUNTIME_MISSING: this release is a Power-only bundle; "
            "use a full bootstrap release"
        )
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    runtime_root = (release_root / str(runtime_manifest.get("root", "runtime"))).resolve()
    if not runtime_root.is_dir():
        raise SetupError(f"release runtime root missing: {runtime_root}")

    state_path = workspace / ".dw" / "release-runtime.json"
    previous: dict[str, Any] = {}
    if state_path.is_file():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
    previous_files = previous.get("files", {}) if isinstance(previous.get("files"), dict) else {}
    copied: list[str] = []
    replaced: list[str] = []
    preserved: list[str] = []
    expected_files: dict[str, str] = {}
    preserve_conflicts = {"AGENTS.md", "requirements-dev.txt", "dw.ps1", "dw.cmd"}

    for entry in runtime_manifest.get("files", []):
        relative = str(entry.get("path", ""))
        source = (runtime_root / relative).resolve()
        destination = (workspace / relative).resolve()
        try:
            source.relative_to(runtime_root)
            destination.relative_to(workspace.resolve())
        except ValueError as exc:
            raise SetupError(f"runtime path escapes root: {relative}") from exc
        if not source.is_file():
            raise SetupError(f"release runtime file missing: {relative}")
        expected = str(entry.get("sha256", ""))
        expected_files[relative] = expected
        if destination.is_file() and not destination.is_symlink() and sha256_file(destination) == expected:
            continue
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink():
                if not repair:
                    raise SetupError(f"BLOCKED_UNMANAGED_RUNTIME: symlink at {destination}; use --repair")
                managed = False
            else:
                managed = previous_files.get(relative) == sha256_file(destination) if destination.is_file() else False
            if not managed and relative in preserve_conflicts:
                preserved.append(relative)
                continue
            if not managed and not repair:
                raise SetupError(
                    f"BLOCKED_UNMANAGED_RUNTIME: {destination}; rerun with --repair after review"
                )
            backup_path(destination, backup_root / "runtime", relative)
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
            replaced.append(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        mode = entry.get("mode")
        if isinstance(mode, str) and re.fullmatch(r"[0-7]{3,4}", mode):
            destination.chmod(int(mode, 8))
        copied.append(relative)

    atomic_json(
        state_path,
        {
            "apiVersion": "dw.superapps/bootstrap-state/v1",
            "releaseRuntime": str(runtime_manifest_path.name),
            "files": {
                relative: digest
                for relative, digest in expected_files.items()
                if relative not in preserved
            },
            "preserved": preserved,
        },
    )
    return {"status": "PASS", "copied": copied, "replaced": replaced, "preserved": preserved}


def ensure_git_repository(workspace: Path) -> str:
    if (workspace / ".git").exists():
        return "existing"
    result = subprocess.run(
        ["git", "init"], cwd=workspace, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise SetupError(f"BLOCKED_GIT_INIT: {(result.stderr or result.stdout).strip()}")
    return "initialized"


def backup_workspace_file(workspace_file: Path, backup_root: Path) -> str:
    destination = backup_root / "workspace.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(workspace_file, destination)
    return str(destination)


def merge_workspace_defaults(data: dict[str, Any], workspace_id: str, workspace_name: str, repair: bool) -> dict[str, Any]:
    defaults = template_workspace(workspace_id, workspace_name)
    if data.get("apiVersion") != "ai-workspace/v1" or data.get("kind") != "Workspace":
        raise SetupError("workspace.yaml has an unsupported apiVersion/kind")
    if "systems" in data:
        raise SetupError(
            "workspace systems registry is removed; move target configuration under projects[]"
        )
    metadata = data.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise SetupError("workspace.yaml metadata must be a mapping")
    current_id = metadata.get("id")
    if current_id and current_id != workspace_id:
        if not repair:
            raise SetupError(
                f"BLOCKED_WORKSPACE_ID_CONFLICT: existing={current_id}, requested={workspace_id}; use --repair"
            )
        metadata["id"] = workspace_id
    else:
        metadata.setdefault("id", workspace_id)
    metadata.setdefault("name", workspace_name)

    for key, value in defaults.items():
        if key not in data:
            data[key] = value
        elif isinstance(value, dict) and isinstance(data[key], dict):
            for child, child_value in value.items():
                data[key].setdefault(child, child_value)
    for key in ("projects", "powers", "hosts", "providers"):
        if not isinstance(data.get(key), list):
            raise SetupError(f"workspace.yaml {key} must be a list")
    return data


def validate_setup_registry(data: dict[str, Any], workspace: Path) -> None:
    """Reject a structurally valid but unusable stale registry before setup."""

    if "systems" in data:
        raise SetupError(
            "workspace systems registry is removed; move target configuration under projects[]"
        )
    hosts = data.get("hosts")
    if not isinstance(hosts, list) or not hosts or any(host not in DEFAULT_HOSTS for host in hosts):
        raise SetupError("workspace hosts are missing or unsupported")

    projects = data.get("projects") or []
    if not isinstance(projects, list):
        raise SetupError("workspace projects must be a list")
    project_ids: set[str] = set()
    project_paths: set[str] = set()
    project_rows: dict[str, dict[str, Any]] = {}
    for project in projects:
        if not isinstance(project, dict):
            raise SetupError("workspace project entries must be mappings")
        project_id = project.get("id")
        if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
            raise SetupError(f"invalid project id: {project_id!r}")
        if project_id in project_ids:
            raise SetupError(f"duplicate project id: {project_id}")
        project_path = project.get("path")
        if not isinstance(project_path, str) or not project_path.strip():
            raise SetupError(f"project {project_id} requires path")
        relative = safe_relative(workspace, project_path).as_posix()
        if relative in project_paths:
            raise SetupError(f"duplicate project path: {relative}")
        source = project.get("source") or project.get("repository")
        if not isinstance(source, str):
            raise SetupError(f"project {project_id} requires owner/name source")
        normalize_repository(source)
        roles = project.get("roles") or []
        if not isinstance(roles, list) or not roles or set(map(str, roles)) - PROJECT_ROLES:
            raise SetupError(f"project {project_id} has invalid roles")
        powers = project.get("powers") or {}
        if not isinstance(powers, dict):
            raise SetupError(f"project {project_id} powers must be a mapping")
        enabled = powers.get("enabled") or []
        if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
            raise SetupError(f"project {project_id} powers.enabled must be a string list")
        project_ids.add(project_id)
        project_paths.add(relative)
        project_rows[project_id] = project

    distribution = data.get("distribution")
    if not isinstance(distribution, dict) or distribution.get("ownership") != "workspace":
        raise SetupError("workspace distribution is missing or not workspace-owned")
    configured_store_root(workspace, data)


def ensure_workspace(
    release_root: Path,
    workspace: Path,
    workspace_id: str,
    workspace_name: str,
    backup_root: Path,
    repair: bool,
) -> dict[str, Any]:
    if not PROJECT_ID.fullmatch(workspace_id):
        raise SetupError(f"invalid workspace id: {workspace_id}")
    if not workspace_name.strip():
        raise SetupError("workspace name cannot be empty")
    workspace_file = workspace / "workspace.yaml"
    changed = False
    backup = None
    if not workspace_file.exists():
        atomic_text(workspace_file, render_workspace_template(release_root, workspace_id, workspace_name))
        changed = True
        data = load_yaml_file(workspace_file) if yaml is not None else template_workspace(workspace_id, workspace_name)
    else:
        if yaml is None:
            raise SetupError(
                "BLOCKED_PYTHON_DEPENDENCY: existing workspace.yaml requires PyYAML for safe stale/broken repair"
            )
        try:
            data = load_yaml_file(workspace_file)
            data = merge_workspace_defaults(data, workspace_id, workspace_name, repair)
            validate_setup_registry(data, workspace)
        except SetupError:
            if not repair:
                raise
            backup = backup_workspace_file(workspace_file, backup_root)
            data = template_workspace(workspace_id, workspace_name)
        rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        original = workspace_file.read_text(encoding="utf-8")
        if rendered != original:
            if repair and backup is None:
                backup = backup_workspace_file(workspace_file, backup_root)
            atomic_text(workspace_file, rendered)
            changed = True
    (workspace / ".dw" / "inbox" / "powers").mkdir(parents=True, exist_ok=True)
    return {"status": "PASS", "changed": changed, "backup": backup, "path": str(workspace_file)}


def detect_repository(project: Path) -> str | None:
    if not (project / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return normalize_repository(raw)
    except SetupError:
        return None


def register_project(
    workspace: Path,
    data: dict[str, Any],
    project_id: str,
    project_path: str,
    project_source: str | None,
    system_id: str | None,
    power_ids: list[str],
    repair: bool,
) -> tuple[dict[str, Any], Path, str]:
    if not PROJECT_ID.fullmatch(project_id):
        raise SetupError(f"invalid project id: {project_id}")
    relative = safe_relative(workspace, project_path)
    target = workspace / relative
    target.mkdir(parents=True, exist_ok=True)
    source = normalize_repository(project_source) if project_source else detect_repository(target)
    if not source:
        raise SetupError(
            f"PROJECT_SOURCE_REQUIRED: provide --project-source owner/name for local target {relative}"
        )
    if system_id and system_id != project_id:
        raise SetupError(
            f"BLOCKED_TARGET_ID_CONFLICT: project={project_id}, deprecated system id={system_id}"
        )
    project_key = project_id
    if not PROJECT_ID.fullmatch(project_key):
        raise SetupError(f"invalid project target id: {project_key}")

    projects = data.setdefault("projects", [])
    project = next((item for item in projects if isinstance(item, dict) and item.get("id") == project_id), None)
    path_owner = next((item for item in projects if isinstance(item, dict) and item.get("path") == relative.as_posix() and item is not project), None)
    if path_owner:
        raise SetupError(f"project path already belongs to {path_owner.get('id')}: {relative}")
    if project is None:
        project = {
            "id": project_id,
            "path": relative.as_posix(),
            "source": source,
            "roles": ["product"],
            "sourceMode": "offline-local",
            "powers": {"enabled": list(power_ids)},
        }
        projects.append(project)
    else:
        existing_source = project.get("source")
        source_conflict = False
        if existing_source:
            try:
                source_conflict = normalize_repository(str(existing_source)) != source
            except SetupError:
                source_conflict = True
        else:
            source_conflict = True
        if (project.get("path") != relative.as_posix() or source_conflict) and not repair:
            raise SetupError(f"BLOCKED_PROJECT_REGISTRATION_CONFLICT: {project_id}; use --repair")
        project.update({"path": relative.as_posix(), "source": source, "sourceMode": "offline-local"})
        project["roles"] = list(dict.fromkeys([role for role in project.get("roles") or [] if role != "system"]))
        if "product" not in project["roles"] and "runtime-target" not in project["roles"]:
            project["roles"].append("product")
        project["powers"] = {"enabled": list(power_ids)}
    return data, target, project_key


def install_power_for_setup(
    release_root: Path,
    component: dict[str, Any],
    workspace: Path,
    store_root: Path,
    target: Path | None,
    system_id: str | None,
    backup_root: Path,
    repair: bool,
) -> dict[str, Any]:
    power_id = str(component["name"])
    package = release_root / str(component["package"])
    package_manifest, manifest_bytes = verify_package_archive(package, power_id)
    destination = store_root / power_id
    source_manifest_sha = sha256_bytes(manifest_bytes)
    action = "installed"
    previous_marker: dict[str, Any] | None = None
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            if not repair:
                raise SetupError(f"BLOCKED_UNMANAGED_PACKAGE: symlink at {destination}; use --repair")
            destination.unlink()
        else:
            marker_path = destination / ".dw-managed.json"
            if marker_path.is_file():
                try:
                    previous_marker = json.loads(marker_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    previous_marker = None
            if previous_marker and previous_marker.get("sourceManifestSha256") == source_manifest_sha:
                try:
                    verify_installed_package(destination, package_manifest)
                except SetupError:
                    if not repair:
                        raise
                    backup_path(destination, backup_root / "powers", f"{power_id}-corrupt")
                    shutil.rmtree(destination)
                    action = "replaced"
                else:
                    action = "unchanged"
            else:
                if not previous_marker and not repair:
                    raise SetupError(f"BLOCKED_UNMANAGED_PACKAGE: {destination}; use --repair")
                if action != "unchanged":
                    backup_path(destination, backup_root / "powers", f"{power_id}-previous")
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()
                    action = "replaced"
    if action != "unchanged":
        store_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{power_id}.", dir=store_root))
        temporary_destination = temporary / "package"
        try:
            install_component(package, temporary_destination, False)
            atomic_json(
                temporary_destination / ".dw-managed.json",
                {
                    "managedBy": "dw-superapps-full-release",
                    "powerId": power_id,
                    "version": package_manifest["metadata"]["version"],
                    "sourceManifestSha256": source_manifest_sha,
                    "installedAtEpoch": int(time.time()),
                },
            )
            os.replace(temporary_destination, destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    result: dict[str, Any] = {
        "powerId": power_id,
        "version": package_manifest["metadata"]["version"],
        "action": action,
        "storePath": str(destination),
        "legacy": {"status": "NONE", "path": str((target / ".dw" / "powers" / power_id) if target else "")},
    }
    if target is not None and system_id is not None:
        legacy = target / ".dw" / "powers" / power_id
        result["legacy"] = {
            "status": "LEGACY_TARGET_INSTALL" if legacy.exists() else "NONE",
            "path": str(legacy),
            "action": "preserved" if legacy.exists() else "none",
        }
        runtime_relative = Path(str(package_manifest["spec"]["runtimeDataRoot"]))
        runtime = (target / runtime_relative).resolve()
        try:
            runtime.relative_to(target.resolve())
        except ValueError as exc:
            raise SetupError(f"runtime root escapes target: {runtime_relative}") from exc
        runtime.mkdir(parents=True, exist_ok=True)
        binding = workspace_binding_path(workspace, system_id, power_id)
        atomic_json(
            binding,
            {
                "apiVersion": "dw.superapps/power-binding/v1",
                "systemId": system_id,
                "targetPath": str(target.resolve()),
                "powerId": power_id,
                "packageVersion": package_manifest["metadata"]["version"],
                "packageManifestSha256": source_manifest_sha,
                "storePath": str(destination.resolve()),
                "runtimePath": str(runtime),
                "updatedAtEpoch": int(time.time()),
            },
        )
        result.update({"runtimePath": str(runtime), "binding": str(binding)})
    return result


def verify_installed_package(destination: Path, package_manifest: dict[str, Any]) -> None:
    """Verify a managed package directory before treating it as unchanged."""

    for entry in package_manifest.get("files", []):
        relative = str(entry.get("path", ""))
        path = (destination / relative).resolve()
        try:
            path.relative_to(destination.resolve())
        except ValueError as exc:
            raise SetupError(f"installed package path escapes store: {relative}") from exc
        if not path.is_file() or path.stat().st_size != entry.get("size"):
            raise SetupError(f"installed package file missing or wrong size: {destination.name}/{relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise SetupError(f"installed package checksum mismatch: {destination.name}/{relative}")
    for entrypoint in package_manifest.get("spec", {}).get("entrypoints", []):
        path = destination / str(entrypoint)
        if not path.is_file():
            raise SetupError(f"installed package entrypoint missing: {destination.name}/{entrypoint}")


def workspace_binding_path(workspace: Path, system_id: str, power_id: str) -> Path:
    path = workspace / ".dw" / "bindings" / system_id / f"{power_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def configured_store_root(workspace: Path, data: dict[str, Any]) -> Path:
    distribution = data.get("distribution") or {}
    value = distribution.get("storeRoot", ".dw/powers")
    if not isinstance(value, str) or not value.strip():
        raise SetupError("workspace distribution.storeRoot must be a path string")
    return workspace / safe_relative(workspace, value)


def run_runtime_command(workspace: Path, arguments: list[str]) -> dict[str, Any]:
    launcher = workspace / "bin" / "dw"
    if not launcher.is_file():
        return {"status": "BLOCKED", "reason": f"missing runtime launcher: {launcher}"}
    result = subprocess.run(
        [str(launcher), *arguments], cwd=workspace, text=True, capture_output=True, check=False
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAILED",
        "returncode": result.returncode,
        "command": [str(launcher), *arguments],
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def setup_release(args: argparse.Namespace) -> dict[str, Any]:
    release_root = Path(args.release).resolve()
    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    manifest = verify_release(release_root)
    component_by_id = {str(item["name"]): item for item in manifest["spec"]["components"]}
    requested = [item.strip() for item in str(args.powers).split(",") if item.strip()]
    power_ids = list(component_by_id) if requested == ["all"] or not requested else requested
    unknown = [power_id for power_id in power_ids if power_id not in component_by_id]
    if unknown:
        raise SetupError(f"unknown release Powers: {unknown}")

    project_id = args.project_id
    project_path = args.project_path
    if bool(project_id) != bool(project_path):
        raise SetupError("child setup requires both --project-id and --project-path")
    if project_id and project_path == ".":
        raise SetupError(
            "root project runtime is not supported because .dw/powers would overlap the runtime target; "
            "use root package mode or a child --project-path"
        )
    if project_id and not args.project_source:
        # A local git remote is acceptable metadata discovery, but no online check is performed.
        candidate = workspace / safe_relative(workspace, project_path)
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)

    history_root = workspace / ".dw" / "history" / "offline-releases"
    history_root.mkdir(parents=True, exist_ok=True)
    backup_root = next_history_path(history_root)
    backup_root.mkdir(parents=True, exist_ok=False)

    git_state = ensure_git_repository(workspace)
    runtime = install_runtime(release_root, workspace, backup_root, args.repair)
    workspace_state = ensure_workspace(
        release_root,
        workspace,
        args.workspace_id,
        args.workspace_name,
        backup_root,
        args.repair,
    )

    data: dict[str, Any]
    target: Path | None = None
    system_id: str | None = None
    registration: dict[str, Any] = {"status": "ROOT_PACKAGE_STORE_ONLY"}
    if project_id and project_path:
        data = load_yaml_file(workspace / "workspace.yaml")
        data, target, system_id = register_project(
            workspace,
            data,
            project_id,
            project_path,
            args.project_source,
            args.system_id,
            power_ids,
            args.repair,
        )
        atomic_text(
            workspace / "workspace.yaml",
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        )
        registration = {
            "status": "REGISTERED",
            "projectId": project_id,
            "projectPath": str(target),
            "systemId": system_id,
        }

    data = load_yaml_file(workspace / "workspace.yaml") if yaml is not None else template_workspace(args.workspace_id, args.workspace_name)
    store_root = configured_store_root(workspace, data)
    installed = [
        install_power_for_setup(
            release_root,
            component_by_id[power_id],
            workspace,
            store_root,
            target,
            system_id,
            backup_root,
            args.repair,
        )
        for power_id in power_ids
    ]

    activation: dict[str, Any]
    if yaml is None:
        activation = {
            "status": "BLOCKED",
            "reason": "PyYAML unavailable; package store is installed but host/doctor commands were not run",
        }
    else:
        activation = {
            "host": run_runtime_command(workspace, ["host", "install", "all", "--mode", "wrapper"]),
            "validate": run_runtime_command(workspace, ["validate"]),
        }
        if target is not None:
            activation["hostStatus"] = run_runtime_command(workspace, ["host", "status", "all"])
            activation["doctors"] = [
                run_runtime_command(workspace, ["power", "doctor", power_id, "--target", str(target)])
                for power_id in power_ids
            ]

    checks = [runtime["status"] == "PASS", workspace_state["status"] == "PASS"]
    checks.extend(item["action"] in {"installed", "replaced", "unchanged"} for item in installed)
    if target is not None:
        checks.append(registration["status"] == "REGISTERED")
        checks.append(activation.get("validate", {}).get("status") == "PASS")
        checks.append(activation.get("host", {}).get("status") == "PASS")
        checks.extend(item.get("status") == "PASS" for item in activation.get("doctors", []))
    # A root-only run proves the shared package store and control plane, but it
    # has no project-owned runtime target to bind or doctor. Keep that state
    # explicit so a package-store bootstrap is never mistaken for a complete
    # project setup.
    status = "READY" if target is not None and all(checks) else "PARTIAL"
    result = {
        "status": status,
        "release": str(release_root),
        "releaseVersion": manifest["metadata"]["version"],
        "workspace": str(workspace),
        "workspaceId": args.workspace_id,
        "git": git_state,
        "backup": str(backup_root),
        "runtime": runtime,
        "workspaceState": workspace_state,
        "registration": registration,
        "powers": installed,
        "activation": activation,
        "remoteAcquisition": "SKIPPED_OFFLINE",
    }
    atomic_json(backup_root / "setup-result.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


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
    parser = argparse.ArgumentParser(description="Verify, install, or bootstrap offline release assets.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--release", required=True)

    install = sub.add_parser("install")
    install.add_argument("--release", required=True)
    install.add_argument("--workspace", required=True)
    install.add_argument("--force", action="store_true")

    setup = sub.add_parser(
        "setup",
        help="bootstrap/repair a Super Project, register an optional child, and install Powers",
    )
    setup.add_argument("--release", required=True)
    setup.add_argument("--workspace", required=True)
    setup.add_argument("--workspace-id", required=True)
    setup.add_argument("--workspace-name", required=True)
    setup.add_argument("--project-id")
    setup.add_argument("--project-path")
    setup.add_argument("--project-source")
    setup.add_argument("--system-id")
    setup.add_argument("--powers", default="all")
    setup.add_argument(
        "--repair",
        action="store_true",
        help="replace stale managed files and back up broken/unmanaged DW control-plane files",
    )

    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--workspace", required=True)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "verify":
            verify_release(Path(args.release).resolve())
            print(json.dumps({"result": "VERIFY_OK"}, indent=2))
        elif args.cmd == "install":
            install_release(args)
        elif args.cmd == "setup":
            setup_release(args)
        elif args.cmd == "rollback":
            rollback(args)
    except (SetupError, OSError, ValueError) as exc:
        print(f"dw-release: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
