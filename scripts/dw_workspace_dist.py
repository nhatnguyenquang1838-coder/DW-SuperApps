#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    print("Missing PyYAML. Run: python -m pip install -r requirements-dev.txt", file=sys.stderr)
    raise SystemExit(2) from exc

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PATH = ROOT / "workspace.yaml"
MANIFEST_DIR = ROOT / "manifests" / "powers"
GENERATED_MARKER = "<!-- generated-by: dw host install -->"
GENERATED_JSON_KEY = "generatedBy"

HOST_SPECS: dict[str, dict[str, str]] = {
    "kiro": {"kind": "skills", "root": ".kiro/skills"},
    "codex": {"kind": "skills", "root": ".codex/skills"},
    "claude": {"kind": "skills", "root": ".claude/skills", "index": "CLAUDE.md"},
    "custom": {"kind": "skills", "root": ".agents/skills", "index": ".agents/DW_AGENT.md"},
    "copilot": {
        "kind": "skills",
        "root": ".github/skills",
        "index": ".github/copilot-instructions.md",
    },
    "cline": {"kind": "instructions", "file": ".clinerules/00-dw-superapps.md"},
    "kilo": {"kind": "instructions", "file": ".kilo/rules/dw-superapps.md"},
}
HOST_ALIASES = {"bionics": "custom", "biotic": "custom", "ollama": "custom"}


class DistError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DistError(f"missing file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DistError(f"expected YAML mapping: {path}")
    return data


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DistError(f"missing file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DistError(f"expected JSON object: {path}")
    return data


def workspace() -> dict[str, Any]:
    return load_yaml(WORKSPACE_PATH)


def manifests() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.yaml")):
        data = load_yaml(path)
        power_id = data.get("metadata", {}).get("id")
        if isinstance(power_id, str) and power_id:
            result[power_id] = data
    return result


def resolve_workspace_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def store_root() -> Path:
    distribution = workspace().get("distribution", {}) or {}
    if not isinstance(distribution, dict):
        raise DistError("workspace distribution must be a mapping")
    value = distribution.get("storeRoot", ".dw/powers")
    if not isinstance(value, str) or not value:
        raise DistError("workspace distribution.storeRoot must be a path string")
    return resolve_workspace_path(value)


def find_system(system_id: str) -> dict[str, Any]:
    for system in workspace().get("systems", []):
        if isinstance(system, dict) and system.get("id") == system_id:
            return system
    raise DistError(f"unknown system: {system_id}")


def normalize_host(host: str) -> str:
    normalized = HOST_ALIASES.get(host, host)
    if normalized not in HOST_SPECS:
        raise DistError(f"unknown host: {host}")
    return normalized


def configured_hosts() -> list[str]:
    result: list[str] = []
    for host in workspace().get("hosts", []):
        normalized = normalize_host(str(host))
        if normalized not in result:
            result.append(normalized)
    return result


def select_hosts(host: str) -> list[str]:
    if host == "all":
        return configured_hosts()
    return [normalize_host(host)]


def installed_entrypoints(power_id: str) -> list[Path]:
    package = store_root() / power_id
    package_manifest = package / "MANIFEST.json"
    if not package_manifest.is_file():
        return []
    data = load_json(package_manifest)
    if data.get("metadata", {}).get("powerId") != power_id:
        raise DistError(f"installed package identity mismatch: {package_manifest}")
    result: list[Path] = []
    for relative in data.get("spec", {}).get("entrypoints", []):
        candidate = package / str(relative)
        if candidate.is_file():
            result.append(candidate)
    return result


def source_entrypoints(power_id: str, manifest: dict[str, Any]) -> list[Path]:
    root = ROOT / manifest["spec"]["path"]
    result: list[Path] = []
    for relative in manifest["spec"]["entrypoints"]["skillCandidates"]:
        candidate = root / relative
        if candidate.is_file():
            result.append(candidate)
    return result


def resolve_skill_source(power_id: str, manifest: dict[str, Any]) -> tuple[Path | None, str]:
    installed = installed_entrypoints(power_id)
    if installed:
        return installed[0].parent, "workspace-store"
    source = source_entrypoints(power_id, manifest)
    if source:
        return source[0].parent, "source-submodule-fallback"
    return None, "missing"


def display_path(path: Path | None) -> str:
    if path is None:
        return "missing"
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(content)
            temporary = handle.name
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def is_generated_path(path: Path) -> bool:
    if path.is_symlink():
        return True
    if not path.exists():
        return False
    if path.is_file():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if GENERATED_MARKER in text:
            return True
        if path.suffix == ".json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return False
            return data.get(GENERATED_JSON_KEY) == "dw"
        return False
    marker = path / "SKILL.md"
    return marker.is_file() and GENERATED_MARKER in marker.read_text(
        encoding="utf-8", errors="ignore"
    )


def safe_remove_generated(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not is_generated_path(path):
        raise DistError(f"refusing to replace non-generated adapter: {display_path(path)}")
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def write_generated(path: Path, content: str) -> None:
    if path.exists() or path.is_symlink():
        safe_remove_generated(path)
    atomic_write(path, content)


def wrapper_content(
    host: str,
    power_id: str,
    manifest: dict[str, Any],
    source: Path | None,
    source_mode: str,
) -> str:
    metadata = manifest["metadata"]
    spec = manifest["spec"]
    package = store_root() / power_id
    orchestration_section = ""
    try:
        system = find_system("rental-home")
        block = system.get("orchestration")
        if isinstance(block, dict):
            primary = block.get("primary", "")
            workers = block.get("workers", [])
            hooks = block.get("hooks", [])
            lines = [
                "## Orchestration",
                "",
                "This adapter is part of a GWC-core orchestrated workspace.",
            ]
            if primary:
                lines.append(f"- Primary governance workflow: `{primary}`")
            if workers:
                lines.append("- Worker powers: " + ", ".join(f"`{w}`" for w in workers))
            if hooks:
                lines.append("- Delegation hooks:")
                for hook in hooks:
                    gate = hook.get("gate", "")
                    worker = hook.get("worker", "")
                    intents = hook.get("intents", [])
                    output_into = hook.get("output_into", "")
                    lines.append(
                        f"  - Gate `{gate}` → `{worker}` for intents {', '.join(intents)}; feed into `{output_into}`"
                    )
            lines.append(
                f"- Use `dw orchestrator prompt --system rental-home --task \"<task>\"` for composed orchestrated prompts."
            )
            orchestration_section = "\n" + "\n".join(lines) + "\n"
    except DistError:
        orchestration_section = ""
    return f"""---
name: dw-{power_id}
description: {metadata['description']}
---
{GENERATED_MARKER}

# {metadata['name']} Power

Thin `{host}` adapter owned by DW-SuperApps.

- Workspace package store: `{display_path(store_root())}`
- Installed package: `{display_path(package)}`
- Resolved entrypoint: `{display_path(source)}`
- Resolution mode: `{source_mode}`
- Source fallback: `{spec['path']}`
- Power manifest: `manifests/powers/{power_id}.yaml`
{orchestration_section}
## Invocation

1. Read `workspace.yaml` and `AGENTS.md` from DW-SuperApps.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Prefer the installed package entrypoint above; use source fallback only when no managed package exists.
5. Keep runtime and project configuration under the target system's `{spec['runtimeDataRoot']}/`.
6. Never create `.dw/powers`, host skill payloads, or distribution history inside the target system.

Generate a complete task prompt with:

`dw power prompt {power_id} --system <system> --task \"<task>\"`
"""


def host_instruction_content(host: str) -> str:
    lines = []
    for power_id, manifest in sorted(manifests().items()):
        source, mode = resolve_skill_source(power_id, manifest)
        lines.append(
            f"- `{power_id}` — store `{display_path(store_root() / power_id)}`; "
            f"entrypoint `{display_path(source)}`; resolution `{mode}`; "
            f"runtime `{manifest['spec']['runtimeDataRoot']}/`."
        )
    orchestration_section = ""
    try:
        system = find_system("rental-home")
        block = system.get("orchestration")
        if isinstance(block, dict):
            primary = block.get("primary", "")
            workers = block.get("workers", [])
            hooks = block.get("hooks", [])
            orchestration_section = "\n## Orchestration for rental-home\n\n"
            if primary:
                orchestration_section += f"- Primary: `{primary}`\n"
            if workers:
                orchestration_section += "- Workers: " + ", ".join(f"`{w}`" for w in workers) + "\n"
            if hooks:
                orchestration_section += "- Delegation hooks:\n"
                for hook in hooks:
                    gate = hook.get("gate", "")
                    worker = hook.get("worker", "")
                    intents = hook.get("intents", [])
                    output_into = hook.get("output_into", "")
                    orchestration_section += (
                        f"  - Gate `{gate}` → `{worker}` for intents "
                        f"{', '.join(intents)}; feed into `{output_into}`\n"
                    )
            orchestration_section += (
                "\nUse `dw orchestrator prompt --system rental-home --task \"<task>\"` for composed prompts.\n"
            )
    except DistError:
        orchestration_section = ""
    prefix = "@AGENTS.md\n\n" if host == "claude" else ""
    return (
        prefix
        + f"""{GENERATED_MARKER}

# DW SuperApps — {host} adapter

Read `AGENTS.md` and `workspace.yaml` before acting.

## Registered Powers

{os.linesep.join(lines)}

## Routing

1. Resolve the target system from `workspace.yaml`.
2. Load Power code from the workspace distribution store first.
3. Use source submodules only as an explicit compatibility fallback.
4. Keep runtime and project configuration inside the selected system repository.
5. Keep packages, inbox, history, bindings, router, and all host adapters in DW-SuperApps.
6. Never install Power skill payloads into a registered system.
{orchestration_section}
Generate a host-neutral prompt:

`dw power prompt <power> --system <system> --task \"<task>\"`
"""
    )


def kilo_config_content() -> str:
    return f"""// {GENERATED_MARKER}
{{
  \"$schema\": \"https://app.kilo.ai/config.json\",
  \"instructions\": [
    \"AGENTS.md\",
    \".kilo/rules/*.md\"
  ]
}}
"""


def install_skill_host(host: str, mode: str) -> None:
    spec = HOST_SPECS[host]
    host_root = ROOT / spec["root"]
    host_root.mkdir(parents=True, exist_ok=True)
    for power_id, manifest in sorted(manifests().items()):
        if host not in manifest["spec"]["hosts"]:
            continue
        destination = host_root / power_id
        source, source_mode = resolve_skill_source(power_id, manifest)
        if destination.exists() or destination.is_symlink():
            safe_remove_generated(destination)
        if mode == "link" and source is not None:
            target = os.path.relpath(source, start=destination.parent)
            destination.symlink_to(target, target_is_directory=True)
            print(f"LINK: {display_path(destination)} -> {target} [{source_mode}]")
        elif mode == "copy" and source is not None:
            shutil.copytree(source, destination)
            skill = destination / "SKILL.md"
            if skill.is_file():
                skill.write_text(
                    skill.read_text(encoding="utf-8") + f"\n\n{GENERATED_MARKER}\n",
                    encoding="utf-8",
                )
            print(f"COPY: {display_path(destination)} [{source_mode}]")
        else:
            destination.mkdir(parents=True, exist_ok=True)
            atomic_write(
                destination / "SKILL.md",
                wrapper_content(host, power_id, manifest, source, source_mode),
            )
            print(f"WRAP: {display_path(destination)} [{source_mode}]")
    if "index" in spec:
        index = ROOT / spec["index"]
        write_generated(index, host_instruction_content(host))
        print(f"INDEX: {display_path(index)}")


def install_instruction_host(host: str) -> None:
    spec = HOST_SPECS[host]
    path = ROOT / spec["file"]
    write_generated(path, host_instruction_content(host))
    print(f"RULE: {display_path(path)}")
    if host == "kilo":
        config = ROOT / "kilo.jsonc"
        write_generated(config, kilo_config_content())
        print(f"CONFIG: {display_path(config)}")


def host_install(args: argparse.Namespace) -> int:
    for host in select_hosts(args.host):
        spec = HOST_SPECS[host]
        if spec["kind"] == "skills":
            install_skill_host(host, args.mode)
        else:
            install_instruction_host(host)
    return 0


def expected_host_paths(host: str) -> list[Path]:
    host = normalize_host(host)
    spec = HOST_SPECS[host]
    paths: list[Path] = []
    if spec["kind"] == "skills":
        root = ROOT / spec["root"]
        for power_id, manifest in sorted(manifests().items()):
            if host in manifest["spec"]["hosts"]:
                paths.append(root / power_id / "SKILL.md")
        if "index" in spec:
            paths.append(ROOT / spec["index"])
    else:
        paths.append(ROOT / spec["file"])
        if host == "kilo":
            paths.append(ROOT / "kilo.jsonc")
    return paths


def host_status(args: argparse.Namespace) -> int:
    failed = False
    for host in select_hosts(args.host):
        for path in expected_host_paths(host):
            state = "ready" if path.exists() else "missing"
            failed = failed or state == "missing"
            print(f"{host:<10} {display_path(path):<64} {state}")
    return 1 if failed else 0


def power_prompt(args: argparse.Namespace) -> int:
    all_manifests = manifests()
    if args.power_id not in all_manifests:
        raise DistError(f"unknown Power: {args.power_id}")
    manifest = all_manifests[args.power_id]
    system = find_system(args.system_id)
    if args.power_id not in system.get("enabled_powers", []):
        raise DistError(f"Power {args.power_id} is not enabled for system {args.system_id}")
    source, mode = resolve_skill_source(args.power_id, manifest)
    system_path = resolve_workspace_path(system["path"])
    runtime = system_path / manifest["spec"]["runtimeDataRoot"]
    legacy = system_path / ".dw" / "powers" / args.power_id
    task = args.task.strip() if args.task else "<describe the task>"
    print(
        f"""Use the `{args.power_id}` Power for system `{args.system_id}`.

Workspace root: `{ROOT}`
Workspace package store: `{store_root()}`
Installed package: `{store_root() / args.power_id}`
Resolved Power entrypoint: `{source if source else 'missing'}`
Resolution mode: `{mode}`
Source fallback: `{ROOT / manifest['spec']['path']}`
System repository: `{system_path}`
System runtime root: `{runtime}`
Legacy target package probe: `{legacy}`

Read in this order:
1. `{ROOT / 'workspace.yaml'}`
2. `{ROOT / 'AGENTS.md'}`
3. `{system_path / 'AGENTS.md'}` when present
4. The resolved installed Power entrypoint above
5. Source fallback only when the managed package is absent

Task:
{task}

Keep generated runtime and configuration inside `{runtime}`.
Keep packages, inbox, cache, history, bindings, router, and host adapters inside `{ROOT}`.
Do not create Power skill payloads or `.dw/powers` inside `{system_path}`.
If `{legacy}` exists, report `LEGACY_TARGET_INSTALL` and leave it untouched.
"""
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dw", description="DW workspace distribution routing")
    commands = result.add_subparsers(dest="command", required=True)

    host = commands.add_parser("host")
    host_commands = host.add_subparsers(dest="host_command", required=True)
    choices = [*HOST_SPECS, *HOST_ALIASES, "all"]
    install = host_commands.add_parser("install")
    install.add_argument("host", nargs="?", choices=choices, default="all")
    install.add_argument("--mode", choices=["wrapper", "link", "copy"], default="wrapper")
    install.set_defaults(handler=host_install)
    status = host_commands.add_parser("status")
    status.add_argument("host", nargs="?", choices=choices, default="all")
    status.set_defaults(handler=host_status)

    power = commands.add_parser("power")
    power_commands = power.add_subparsers(dest="power_command", required=True)
    prompt = power_commands.add_parser("prompt")
    prompt.add_argument("power_id")
    prompt.add_argument("--system", dest="system_id", required=True)
    prompt.add_argument("--task", default="")
    prompt.set_defaults(handler=power_prompt)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(args.handler(args))
    except (DistError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"dw-dist: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
