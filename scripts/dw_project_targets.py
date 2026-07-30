#!/usr/bin/env python3
"""Shared resolution helpers for project-native runtime targets."""
from __future__ import annotations

from pathlib import Path
from typing import Any


TARGET_ROLES = frozenset({"product", "runtime-target"})


class ProjectTargetError(RuntimeError):
    pass


def project_entries(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    rows = workspace.get("projects") or []
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        raise ProjectTargetError("workspace projects must be a list of mappings")
    return rows


def runtime_projects(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        project
        for project in project_entries(workspace)
        if TARGET_ROLES.intersection({str(role) for role in project.get("roles") or []})
    ]


def find_runtime_project(workspace: dict[str, Any], project_id: str) -> dict[str, Any]:
    for project in runtime_projects(workspace):
        if project.get("id") == project_id:
            return project
    raise ProjectTargetError(f"unknown runtime target project: {project_id}")


def enabled_powers(project: dict[str, Any]) -> list[str]:
    powers = project.get("powers") or {}
    if not isinstance(powers, dict):
        raise ProjectTargetError(f"project {project.get('id')} powers must be a mapping")
    enabled = powers.get("enabled") or []
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ProjectTargetError(
            f"project {project.get('id')} powers.enabled must be a string list"
        )
    return list(enabled)


def project_path(project: dict[str, Any], root: Path) -> Path:
    value = project.get("path")
    if not isinstance(value, str) or not value.strip():
        raise ProjectTargetError(f"project {project.get('id')} requires path")
    raw = Path(value)
    if raw.is_absolute():
        raise ProjectTargetError(f"project {project.get('id')} path must be relative: {value}")
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ProjectTargetError(
            f"project {project.get('id')} path escapes workspace: {value}"
        ) from exc
    return resolved
