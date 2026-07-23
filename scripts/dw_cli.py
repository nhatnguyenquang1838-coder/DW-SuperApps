#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    print(
        "Missing PyYAML. Run: python -m pip install -r requirements-dev.txt",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PATH = ROOT / "workspace.yaml"
MANIFEST_DIR = ROOT / "manifests" / "powers"
GENERATED_MARKER = "<!-- generated-by: dw host install -->"


class DwError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DwError(f"missing {path.relative_to(ROOT)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DwError(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return data


def workspace() -> dict[str, Any]:
    return load_yaml(WORKSPACE_PATH)


def manifests() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        manifest = load_yaml(path)
        power_id = manifest.get("metadata", {}).get("id")
        if not isinstance(power_id, str) or not power_id:
            raise DwError(f"{path.relative_to(ROOT)} has no metadata.id")
        if power_id in result:
            raise DwError(f"duplicate Power manifest id: {power_id}")
        result[power_id] = manifest
    return result


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise DwError(detail or f"command failed: {' '.join(args)}")
    return result


def git(*args: str, cwd: Path = ROOT, capture: bool = True) -> str:
    result = run(["git", *args], cwd=cwd, capture=capture)
    return result.stdout.strip() if capture else ""


def emit(data: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def find_system(system_id: str) -> dict[str, Any]:
    for system in workspace().get("systems", []):
        if system.get("id") == system_id:
            return system
    raise DwError(f"unknown system: {system_id}")


def workspace_info(args: argparse.Namespace) -> int:
    ws = workspace()
    data = {
        "id": ws["metadata"]["id"],
        "name": ws["metadata"]["name"],
        "hosts": ws.get("hosts", []),
        "powers": [item["id"] for item in ws.get("powers", []) if item.get("enabled", True)],
        "systems": [item["id"] for item in ws.get("systems", [])],
    }
    if args.json:
        emit(data, as_json=True)
        return 0
    print(f"Workspace: {data['name']} ({data['id']})")
    print(f"Hosts: {', '.join(data['hosts']) or '-'}")
    print(f"Powers: {', '.join(data['powers']) or '-'}")
    print(f"Systems: {', '.join(data['systems']) or '-'}")
    return 0


def power_list(args: argparse.Namespace) -> int:
    rows = []
    for power_id, manifest in sorted(manifests().items()):
        spec = manifest["spec"]
        rows.append(
            {
                "id": power_id,
                "name": manifest["metadata"]["name"],
                "version": manifest["metadata"]["version"],
                "category": spec["category"],
                "provides": spec["provides"],
                "hosts": spec["hosts"],
            }
        )
    if args.json:
        emit(rows, as_json=True)
        return 0
    print(f"{'ID':<12} {'VERSION':<14} {'CATEGORY':<24} PROVIDES")
    for row in rows:
        print(
            f"{row['id']:<12} {row['version']:<14} {row['category']:<24} "
            f"{', '.join(row['provides'])}"
        )
    return 0


def power_info(args: argparse.Namespace) -> int:
    all_manifests = manifests()
    if args.power_id not in all_manifests:
        raise DwError(f"unknown Power: {args.power_id}")
    manifest = all_manifests[args.power_id]
    if args.json:
        emit(manifest, as_json=True)
        return 0
    metadata = manifest["metadata"]
    spec = manifest["spec"]
    print(f"{metadata['name']} ({metadata['id']})")
    print(f"Version: {metadata['version']}")
    print(f"Category: {spec['category']}")
    print(f"Source: {spec['source']}")
    print(f"Path: {spec['path']}")
    print(f"Provides: {', '.join(spec['provides'])}")
    print(f"Consumes: {', '.join(spec.get('consumes', [])) or '-'}")
    print(f"Requires: {', '.join(spec.get('requires', [])) or '-'}")
    print(f"Hosts: {', '.join(spec['hosts'])}")
    print(f"Runtime data: {spec['runtimeDataRoot']}")
    return 0


def power_prompt(args: argparse.Namespace) -> int:
    all_manifests = manifests()
    if args.power_id not in all_manifests:
        raise DwError(f"unknown Power: {args.power_id}")
    manifest = all_manifests[args.power_id]
    system = find_system(args.system_id)
    if args.power_id not in system.get("enabled_powers", []):
        raise DwError(f"Power {args.power_id} is not enabled for system {args.system_id}")
    spec = manifest["spec"]
    skill_candidates = spec["entrypoints"]["skillCandidates"]
    task = args.task.strip() if args.task else "<describe the task>"
    candidate_lines = os.linesep.join(
        f"   - `{spec['path']}/{candidate}`" for candidate in skill_candidates
    )
    print(
        f"""Use the `{args.power_id}` Power for system `{args.system_id}`.

Workspace root: `{ROOT}`
System repository: `{system['path']}`
Power source: `{spec['path']}`
Power manifest: `manifests/powers/{args.power_id}.yaml`
Runtime data root in the system: `{spec['runtimeDataRoot']}`

Read in this order:
1. `workspace.yaml`
2. `AGENTS.md`
3. `{system['path']}/AGENTS.md` when present
4. The first existing Power entrypoint from:
{candidate_lines}

Task:
{task}

Keep generated data inside `{system['path']}/{spec['runtimeDataRoot']}/`.
Do not write generated data into `{spec['path']}`.
"""
    )
    return 0


def submodule_entries() -> list[dict[str, str]]:
    ws = workspace()
    entries: list[dict[str, str]] = []
    for power in ws.get("powers", []):
        entries.append({"type": "power", "id": power["id"], "path": power["path"]})
    for system in ws.get("systems", []):
        entries.append({"type": "system", "id": system["id"], "path": system["path"]})
    return entries


def select_submodules(target: str) -> list[dict[str, str]]:
    entries = submodule_entries()
    if target == "all":
        return entries
    if target == "powers":
        return [item for item in entries if item["type"] == "power"]
    if target == "systems":
        return [item for item in entries if item["type"] == "system"]
    selected = [item for item in entries if item["id"] == target]
    if not selected:
        raise DwError(f"unknown submodule target: {target}")
    return selected


def require_initialized(path: Path) -> None:
    if not (path / ".git").exists():
        raise DwError(f"{path.relative_to(ROOT)} is not initialized; run `dw power init`")


def pinned_sha(relative_path: str) -> str:
    line = git("ls-tree", "HEAD", relative_path)
    if not line:
        raise DwError(f"no gitlink found for {relative_path}")
    return line.split()[2]


def submodule_branch(relative_path: str) -> str:
    result = run(
        [
            "git",
            "config",
            "-f",
            str(ROOT / ".gitmodules"),
            "--get",
            f"submodule.{relative_path}.branch",
        ],
        capture=True,
        check=False,
    )
    return result.stdout.strip() or "main"


def remote_sha(path: Path, branch: str) -> str:
    result = run(
        ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
        cwd=path,
        capture=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return "unavailable"
    return result.stdout.split()[0]


def power_sync(args: argparse.Namespace) -> int:
    selected = select_submodules(args.target)
    paths = [item["path"] for item in selected]
    mode = args.mode

    if mode == "init":
        git("submodule", "sync", "--recursive", capture=False)
        run(["git", "submodule", "update", "--init", "--recursive", "--", *paths])
        return 0

    if mode == "status":
        run(["git", "submodule", "status", "--recursive", "--", *paths])
        return 0

    if mode == "check":
        failed = False
        for item in selected:
            relative_path = item["path"]
            path = ROOT / relative_path
            try:
                require_initialized(path)
            except DwError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                failed = True
                continue
            pinned = pinned_sha(relative_path)
            current = git("-C", relative_path, "rev-parse", "HEAD")
            branch = submodule_branch(relative_path)
            remote = remote_sha(path, branch)
            dirty = bool(git("-C", relative_path, "status", "--porcelain"))
            states = ["pinned" if current == pinned else "working-copy-moved"]
            if remote != "unavailable" and current != remote:
                states.append("remote-drift")
            if dirty:
                states.append("DIRTY")
                failed = True
            print(
                f"{relative_path:<24} pin={pinned[:12]} current={current[:12]} "
                f"remote={remote[:12]} state={','.join(states)}"
            )
        return 1 if failed else 0

    if mode == "update":
        for item in selected:
            relative_path = item["path"]
            path = ROOT / relative_path
            require_initialized(path)
            if git("-C", relative_path, "status", "--porcelain"):
                raise DwError(f"refusing to update dirty submodule {relative_path}")
            branch = submodule_branch(relative_path)
            print(f"Updating {relative_path} -> origin/{branch}")
            run(["git", "fetch", "origin", branch], cwd=path)
            run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=path)
        print(f"Review with: dw power check {args.target}")
        print(f"Stage pins with: dw power pin {args.target}")
        return 0

    if mode == "pin":
        for item in selected:
            relative_path = item["path"]
            path = ROOT / relative_path
            require_initialized(path)
            if git("-C", relative_path, "status", "--porcelain"):
                raise DwError(f"refusing to pin dirty submodule {relative_path}")
            run(["git", "add", relative_path])
        run(["git", "add", ".gitmodules"])
        print("Pins staged. No commit was created.")
        run(["git", "diff", "--cached", "--submodule=short"])
        return 0

    raise DwError(f"unknown sync mode: {mode}")


def resolve_skill_source(power_id: str, manifest: dict[str, Any]) -> Path | None:
    power_root = ROOT / manifest["spec"]["path"]
    for candidate in manifest["spec"]["entrypoints"]["skillCandidates"]:
        skill_file = power_root / candidate
        if skill_file.is_file():
            return skill_file.parent
    return None


def safe_remove_generated(destination: Path) -> None:
    if destination.is_symlink():
        destination.unlink()
        return
    if not destination.exists():
        return
    marker_file = destination / "SKILL.md" if destination.is_dir() else destination
    if marker_file.is_file() and GENERATED_MARKER in marker_file.read_text(
        encoding="utf-8", errors="ignore"
    ):
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
        return
    raise DwError(f"refusing to replace non-generated adapter: {destination.relative_to(ROOT)}")


def wrapper_content(
    host: str,
    power_id: str,
    manifest: dict[str, Any],
    source: Path | None,
) -> str:
    metadata = manifest["metadata"]
    spec = manifest["spec"]
    relative_source = source.relative_to(ROOT).as_posix() if source is not None else spec["path"]
    return f"""---
name: dw-{power_id}
description: {metadata['description']}
---
{GENERATED_MARKER}

# {metadata['name']} Power

This is a thin `{host}` adapter. Canonical behavior remains in:

- Power source: `../../../{spec['path']}`
- Power manifest: `../../../manifests/powers/{power_id}.yaml`
- Preferred entrypoint: `../../../{relative_source}`

## Invocation

1. Read `../../../workspace.yaml` and `../../../AGENTS.md`.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Read the canonical Power entrypoint above.
5. Keep generated data under the target system's `{spec['runtimeDataRoot']}/`.
6. Never store project runtime data in the Power submodule.

Use `dw power prompt {power_id} --system <system> --task "<task>"` to generate a host-neutral invocation prompt.
"""


def install_host_adapters(args: argparse.Namespace) -> int:
    selected_hosts = ["kiro", "codex"] if args.host == "all" else [args.host]
    all_manifests = manifests()
    for host in selected_hosts:
        host_root = ROOT / f".{host}" / "skills"
        host_root.mkdir(parents=True, exist_ok=True)
        for power_id, manifest in sorted(all_manifests.items()):
            if host not in manifest["spec"]["hosts"]:
                continue
            destination = host_root / power_id
            source = resolve_skill_source(power_id, manifest)
            safe_remove_generated(destination)
            if args.mode == "link" and source is not None:
                target = os.path.relpath(source, start=destination.parent)
                destination.symlink_to(target, target_is_directory=True)
                print(f"LINK: {destination.relative_to(ROOT)} -> {target}")
            elif args.mode == "copy" and source is not None:
                shutil.copytree(source, destination)
                skill_file = destination / "SKILL.md"
                skill_file.write_text(
                    skill_file.read_text(encoding="utf-8") + f"\n\n{GENERATED_MARKER}\n",
                    encoding="utf-8",
                )
                print(f"COPY: {destination.relative_to(ROOT)}")
            else:
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "SKILL.md").write_text(
                    wrapper_content(host, power_id, manifest, source),
                    encoding="utf-8",
                )
                print(f"WRAP: {destination.relative_to(ROOT)}")
    return 0


def host_status(args: argparse.Namespace) -> int:
    selected_hosts = ["kiro", "codex"] if args.host == "all" else [args.host]
    all_manifests = manifests()
    failed = False
    for host in selected_hosts:
        for power_id in sorted(all_manifests):
            path = ROOT / f".{host}" / "skills" / power_id / "SKILL.md"
            state = "ready" if path.exists() else "missing"
            failed = failed or state == "missing"
            print(f"{host:<6} {power_id:<12} {state}")
    return 1 if failed else 0


def system_list(args: argparse.Namespace) -> int:
    systems = workspace().get("systems", [])
    if args.json:
        emit(systems, as_json=True)
        return 0
    for system in systems:
        powers = ", ".join(system.get("enabled_powers", []))
        print(f"{system['id']}: {system['path']} [{powers}]")
    return 0


def system_powers(args: argparse.Namespace) -> int:
    system = find_system(args.system_id)
    enabled = system.get("enabled_powers", [])
    if args.json:
        emit(
            {"system": system["id"], "path": system["path"], "enabled_powers": enabled},
            as_json=True,
        )
        return 0
    print(f"System: {system['id']}")
    print(f"Path: {system['path']}")
    print(f"Powers: {', '.join(enabled) or '-'}")
    return 0


def validate(_: argparse.Namespace) -> int:
    return run(
        [sys.executable, str(ROOT / "scripts" / "validate-workspace.py")],
        check=False,
    ).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dw", description="DW SuperApps Power Runtime v2")
    parser.add_argument("--version", action="version", version="dw 2.0")
    commands = parser.add_subparsers(dest="command", required=True)

    workspace_parser = commands.add_parser("workspace")
    workspace_commands = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    workspace_info_parser = workspace_commands.add_parser("info")
    workspace_info_parser.add_argument("--json", action="store_true")
    workspace_info_parser.set_defaults(handler=workspace_info)

    power_parser = commands.add_parser("power")
    power_commands = power_parser.add_subparsers(dest="power_command", required=True)

    power_list_parser = power_commands.add_parser("list")
    power_list_parser.add_argument("--json", action="store_true")
    power_list_parser.set_defaults(handler=power_list)

    power_info_parser = power_commands.add_parser("info")
    power_info_parser.add_argument("power_id")
    power_info_parser.add_argument("--json", action="store_true")
    power_info_parser.set_defaults(handler=power_info)

    power_prompt_parser = power_commands.add_parser("prompt")
    power_prompt_parser.add_argument("power_id")
    power_prompt_parser.add_argument("--system", dest="system_id", required=True)
    power_prompt_parser.add_argument("--task", default="")
    power_prompt_parser.set_defaults(handler=power_prompt)

    for mode in ("init", "check", "update", "pin", "status"):
        mode_parser = power_commands.add_parser(mode)
        mode_parser.add_argument("target", nargs="?", default="all")
        mode_parser.set_defaults(handler=power_sync, mode=mode)

    host_parser = commands.add_parser("host")
    host_commands = host_parser.add_subparsers(dest="host_command", required=True)
    host_install_parser = host_commands.add_parser("install")
    host_install_parser.add_argument(
        "host", nargs="?", choices=["kiro", "codex", "all"], default="all"
    )
    host_install_parser.add_argument(
        "--mode",
        choices=["wrapper", "link", "copy"],
        default="wrapper",
        help="wrapper is cross-platform and does not require symlink privileges",
    )
    host_install_parser.set_defaults(handler=install_host_adapters)

    host_status_parser = host_commands.add_parser("status")
    host_status_parser.add_argument(
        "host", nargs="?", choices=["kiro", "codex", "all"], default="all"
    )
    host_status_parser.set_defaults(handler=host_status)

    system_parser = commands.add_parser("system")
    system_commands = system_parser.add_subparsers(dest="system_command", required=True)
    system_list_parser = system_commands.add_parser("list")
    system_list_parser.add_argument("--json", action="store_true")
    system_list_parser.set_defaults(handler=system_list)
    system_powers_parser = system_commands.add_parser("powers")
    system_powers_parser.add_argument("system_id")
    system_powers_parser.add_argument("--json", action="store_true")
    system_powers_parser.set_defaults(handler=system_powers)

    validate_parser = commands.add_parser("validate")
    validate_parser.set_defaults(handler=validate)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.handler(args))
    except DwError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
