#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace.yaml"
AGENTS = ROOT / "AGENTS.md"
GITIGNORE = ROOT / ".gitignore"
CONTROLLER = ROOT / "controllers" / "taskcontroller.yaml"
OVERLAY = ROOT / "controllers" / "executor-worktree-policy.md"
HERMES = ROOT / "agents" / "hermes" / "agent-instructions.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "ISOLATED_SUBMODULE_WORKTREE.md"

RUNBOOK_REF = "docs/runbooks/ISOLATED_SUBMODULE_WORKTREE.md"
OVERLAY_REF = "controllers/executor-worktree-policy.md"
WORKTREE_TEMPLATE = "worktrees/{project}/{execution_unit}"


class ValidationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"missing required file: {path.relative_to(ROOT)}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"expected YAML mapping: {path.relative_to(ROOT)}")
    return value


def run_git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValidationError(detail or f"git {' '.join(args)} failed")
    return result


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def text(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"missing required file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def project_entries(workspace: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    raw = workspace.get("projects", [])
    require(isinstance(raw, list), "workspace.projects must be a list", errors)
    if not isinstance(raw, list):
        return []
    projects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            errors.append("workspace.projects entries must be mappings")
            continue
        project_id = item.get("id")
        path = item.get("path")
        if not isinstance(project_id, str) or not project_id:
            errors.append("workspace project missing id")
            continue
        if project_id in seen:
            errors.append(f"duplicate workspace project id: {project_id}")
        seen.add(project_id)
        if not isinstance(path, str) or not path.startswith("projects/"):
            errors.append(f"project {project_id} path must be under projects/: {path!r}")
        projects.append(item)
    return projects


def configured_submodule_paths(errors: list[str]) -> set[str]:
    gitmodules = ROOT / ".gitmodules"
    if not gitmodules.is_file():
        errors.append("missing .gitmodules")
        return set()
    result = run_git(
        "config",
        "-f",
        str(gitmodules),
        "--get-regexp",
        r"^submodule\..*\.path$",
        check=False,
    )
    if result.returncode not in (0, 1):
        errors.append((result.stderr or result.stdout).strip() or "unable to parse .gitmodules")
        return set()
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            paths.add(parts[1].strip())
    return paths


def validate_static() -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    workspace = load_yaml(WORKSPACE)
    projects = project_entries(workspace, errors)

    development = workspace.get("development")
    require(isinstance(development, dict), "workspace.development must be a mapping", errors)
    if isinstance(development, dict):
        expected_scalars = {
            "model": "workspace-rooted-child-repository-worktrees",
            "projectAnchorRoot": "projects",
            "worktreeRoot": "worktrees",
            "worktreeTemplate": WORKTREE_TEMPLATE,
            "writableSurface": "child-worktree-only",
            "canonicalRunbook": RUNBOOK_REF,
            "controllerPolicy": OVERLAY_REF,
        }
        for key, expected in expected_scalars.items():
            require(
                development.get(key) == expected,
                f"workspace.development.{key} must equal {expected!r}",
                errors,
            )

        execution = development.get("executionUnit")
        require(isinstance(execution, dict), "workspace.development.executionUnit must be a mapping", errors)
        if isinstance(execution, dict):
            for key in ("oneWorktree", "oneBranch", "oneWriter"):
                require(execution.get(key) is True, f"executionUnit.{key} must be true", errors)
            require(
                execution.get("agentIdentity") == "lease-or-binding-not-branch",
                "executionUnit.agentIdentity must be lease-or-binding-not-branch",
                errors,
            )

        base = development.get("base")
        require(isinstance(base, dict), "workspace.development.base must be a mapping", errors)
        if isinstance(base, dict):
            require(base.get("resolveRemoteBeforeCreate") is True, "base.resolveRemoteBeforeCreate must be true", errors)
            require(base.get("requireExactSha") is True, "base.requireExactSha must be true", errors)

        integration = development.get("integration")
        require(isinstance(integration, dict), "workspace.development.integration must be a mapping", errors)
        if isinstance(integration, dict):
            require(integration.get("childRepositoryPr") == "required", "integration.childRepositoryPr must be required", errors)
            require(integration.get("parentGitlinkPr") == "separate", "integration.parentGitlinkPr must be separate", errors)
            require(integration.get("parentGitlinkMutation") == "explicit", "integration.parentGitlinkMutation must be explicit", errors)
            require(integration.get("parentWriter") == "exclusive", "integration.parentWriter must be exclusive", errors)

        runtime = development.get("runtime")
        require(isinstance(runtime, dict), "workspace.development.runtime must be a mapping", errors)
        if isinstance(runtime, dict):
            require(runtime.get("namespacePerExecutionUnit") is True, "runtime.namespacePerExecutionUnit must be true", errors)

    submodule_paths = configured_submodule_paths(errors)
    for project in projects:
        path = project.get("path")
        if isinstance(path, str):
            require(path in submodule_paths, f"registered project is not a .gitmodules path: {path}", errors)

    agents = text(AGENTS, errors)
    require(RUNBOOK_REF in agents, f"AGENTS.md must route to {RUNBOOK_REF}", errors)
    require(OVERLAY_REF in agents, f"AGENTS.md must route TaskController executors to {OVERLAY_REF}", errors)

    ignore = text(GITIGNORE, errors)
    require(
        any(line.strip() == "/worktrees/" for line in ignore.splitlines()),
        ".gitignore must contain /worktrees/",
        errors,
    )

    text(RUNBOOK, errors)
    text(OVERLAY, errors)

    controller = load_yaml(CONTROLLER)
    required = (
        controller.get("host_overlays", {})
        .get("hermes", {})
        .get("executor", {})
        .get("required", [])
    )
    require(
        isinstance(required, list) and OVERLAY_REF in required,
        f"controllers/taskcontroller.yaml must require {OVERLAY_REF} for Hermes executor routing",
        errors,
    )

    hermes = text(HERMES, errors)
    require(OVERLAY_REF in hermes, f"Hermes instructions must reference {OVERLAY_REF}", errors)
    require(RUNBOOK_REF in hermes, f"Hermes instructions must reference {RUNBOOK_REF}", errors)

    tracked = run_git("ls-files", "worktrees", check=False)
    require(tracked.returncode == 0, "git ls-files worktrees failed", errors)
    require(not tracked.stdout.strip(), "worktrees/ must not contain tracked repository files", errors)

    return errors, projects


def parse_worktree_paths(anchor: Path) -> list[Path]:
    result = run_git("worktree", "list", "--porcelain", cwd=anchor)
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree ") :]).resolve())
    return paths


def validate_runtime(projects: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    root = ROOT.resolve()
    allowed_root = (ROOT / "worktrees").resolve()

    for project in projects:
        project_id = project.get("id")
        relative = project.get("path")
        if not isinstance(project_id, str) or not isinstance(relative, str):
            continue
        anchor = ROOT / relative
        git_marker = anchor / ".git"
        if not git_marker.exists():
            continue

        dirty = run_git("status", "--porcelain", cwd=anchor, check=False)
        if dirty.returncode != 0:
            errors.append(f"unable to inspect project anchor: {relative}")
        elif dirty.stdout.strip():
            errors.append(f"project anchor is dirty; child development must not occur in {relative}")

        try:
            worktrees = parse_worktree_paths(anchor)
        except ValidationError as exc:
            errors.append(f"{project_id}: {exc}")
            continue

        anchor_resolved = anchor.resolve()
        for worktree in worktrees:
            if worktree == anchor_resolved:
                continue
            try:
                relative_worktree = worktree.relative_to(allowed_root)
            except ValueError:
                errors.append(
                    f"{project_id}: linked worktree outside DW-SuperApps/worktrees: {worktree}"
                )
                continue
            parts = relative_worktree.parts
            if len(parts) < 2 or parts[0] != project_id:
                errors.append(
                    f"{project_id}: worktree must match worktrees/{project_id}/<execution-unit>: {worktree}"
                )
            try:
                worktree.relative_to(root)
            except ValueError:
                errors.append(f"{project_id}: worktree is outside DW-SuperApps root: {worktree}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DW-SuperApps isolated submodule worktree policy")
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="also inspect initialized submodule anchors and linked worktree locations",
    )
    args = parser.parse_args()

    try:
        errors, projects = validate_static()
        if args.runtime:
            errors.extend(validate_runtime(projects))
    except ValidationError as exc:
        errors = [str(exc)]

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    mode = "static+runtime" if args.runtime else "static"
    print(f"WORKTREE_POLICY_VALID: {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
