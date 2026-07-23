#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
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
GENERATED_JSON_KEY = "generatedBy"

HOST_SPECS: dict[str, dict[str, str]] = {
    "kiro": {"kind": "skills", "root": ".kiro/skills"},
    "codex": {"kind": "skills", "root": ".codex/skills"},
    "claude": {"kind": "skills", "root": ".claude/skills", "index": "CLAUDE.md"},
    "custom": {"kind": "skills", "root": ".agents/skills", "index": ".agents/DW_AGENT.md"},
    "copilot": {
        "kind": "instructions",
        "file": ".github/instructions/dw-superapps.instructions.md",
    },
    "cline": {"kind": "instructions", "file": ".clinerules/00-dw-superapps.md"},
    "kilo": {"kind": "instructions", "file": ".kilo/rules/dw-superapps.md"},
}
HOST_ALIASES = {
    "bionics": "custom",
    "biotic": "custom",
    "ollama": "custom",
}


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


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=path.parent,
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(content)
            temp_path = handle.name
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def find_system(system_id: str) -> dict[str, Any]:
    for system in workspace().get("systems", []):
        if system.get("id") == system_id:
            return system
    raise DwError(f"unknown system: {system_id}")


def provider_entries() -> list[dict[str, Any]]:
    entries = workspace().get("providers", [])
    if not isinstance(entries, list):
        raise DwError("workspace providers must be a list")
    return [item for item in entries if isinstance(item, dict)]


def find_provider(provider_id: str) -> dict[str, Any]:
    for provider in provider_entries():
        if provider.get("id") == provider_id:
            return provider
    raise DwError(f"unknown provider: {provider_id}")


def workspace_info(args: argparse.Namespace) -> int:
    ws = workspace()
    data = {
        "id": ws["metadata"]["id"],
        "name": ws["metadata"]["name"],
        "hosts": ws.get("hosts", []),
        "providers": [item["id"] for item in provider_entries()],
        "powers": [item["id"] for item in ws.get("powers", []) if item.get("enabled", True)],
        "systems": [item["id"] for item in ws.get("systems", [])],
    }
    if args.json:
        emit(data, as_json=True)
        return 0
    print(f"Workspace: {data['name']} ({data['id']})")
    print(f"Hosts: {', '.join(data['hosts']) or '-'}")
    print(f"Providers: {', '.join(data['providers']) or '-'}")
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


def normalize_host(host: str) -> str:
    normalized = HOST_ALIASES.get(host, host)
    if normalized not in HOST_SPECS:
        raise DwError(f"unknown host: {host}")
    return normalized


def configured_hosts() -> list[str]:
    raw_hosts = workspace().get("hosts", [])
    result: list[str] = []
    for host in raw_hosts:
        normalized = normalize_host(str(host))
        if normalized not in result:
            result.append(normalized)
    return result


def select_hosts(host: str) -> list[str]:
    if host == "all":
        return configured_hosts()
    return [normalize_host(host)]


def resolve_skill_source(power_id: str, manifest: dict[str, Any]) -> Path | None:
    power_root = ROOT / manifest["spec"]["path"]
    for candidate in manifest["spec"]["entrypoints"]["skillCandidates"]:
        skill_file = power_root / candidate
        if skill_file.is_file():
            return skill_file.parent
    return None


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


def safe_remove_generated(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if not is_generated_path(path):
        raise DwError(f"refusing to replace non-generated adapter: {path.relative_to(ROOT)}")
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
    return True


def write_generated_file(path: Path, content: str) -> None:
    if path.exists() or path.is_symlink():
        safe_remove_generated(path)
    atomic_write(path, content)


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

Thin `{host}` adapter. Canonical behavior remains in:

- Power source: `{spec['path']}`
- Power manifest: `manifests/powers/{power_id}.yaml`
- Preferred entrypoint: `{relative_source}`

## Invocation

1. Read `workspace.yaml` and `AGENTS.md`.
2. Resolve one target system from the workspace registry.
3. Read project-local instructions in that system.
4. Read the canonical Power entrypoint above.
5. Keep generated data under the target system's `{spec['runtimeDataRoot']}/`.
6. Never store project runtime data in the Power submodule.

Generate a complete task prompt with:

`dw power prompt {power_id} --system <system> --task "<task>"`
"""


def host_instruction_content(host: str) -> str:
    power_lines = []
    for power_id, manifest in sorted(manifests().items()):
        metadata = manifest["metadata"]
        spec = manifest["spec"]
        power_lines.append(
            f"- `{power_id}` — {metadata['description']} "
            f"Runtime data: `{spec['runtimeDataRoot']}/`."
        )
    prefix = ""
    if host == "copilot":
        prefix = '---\napplyTo: "**"\n---\n'
    if host == "claude":
        prefix = "@AGENTS.md\n\n"
    return (
        prefix
        + f"""{GENERATED_MARKER}

# DW SuperApps — {host} adapter

Read `AGENTS.md` and `workspace.yaml` before acting.

## Registered Powers

{os.linesep.join(power_lines)}

## Routing

1. Resolve the target system from `workspace.yaml`.
2. Use only Powers enabled for that system.
3. Read the first existing `skillCandidates` entry from the Power manifest.
4. Keep runtime data inside the system repository.
5. Do not modify a Power submodule unless the task explicitly targets that Power repository.

Generate a host-neutral prompt:

`dw power prompt <power> --system <system> --task "<task>"`

Validate the workspace:

`dw doctor all`
"""
    )


def kilo_config_content() -> str:
    return f"""// {GENERATED_MARKER}
{{
  "$schema": "https://app.kilo.ai/config.json",
  "instructions": [
    "AGENTS.md",
    ".kilo/rules/*.md"
  ]
}}
"""


def host_expected_paths(host: str) -> list[Path]:
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


def install_skill_host(host: str, mode: str) -> None:
    spec = HOST_SPECS[host]
    host_root = ROOT / spec["root"]
    host_root.mkdir(parents=True, exist_ok=True)
    for power_id, manifest in sorted(manifests().items()):
        if host not in manifest["spec"]["hosts"]:
            continue
        destination = host_root / power_id
        source = resolve_skill_source(power_id, manifest)
        if destination.exists() or destination.is_symlink():
            safe_remove_generated(destination)
        if mode == "link" and source is not None:
            target = os.path.relpath(source, start=destination.parent)
            destination.symlink_to(target, target_is_directory=True)
            print(f"LINK: {destination.relative_to(ROOT)} -> {target}")
        elif mode == "copy" and source is not None:
            shutil.copytree(source, destination)
            skill_file = destination / "SKILL.md"
            skill_file.write_text(
                skill_file.read_text(encoding="utf-8") + f"\n\n{GENERATED_MARKER}\n",
                encoding="utf-8",
            )
            print(f"COPY: {destination.relative_to(ROOT)}")
        else:
            destination.mkdir(parents=True, exist_ok=True)
            atomic_write(destination / "SKILL.md", wrapper_content(host, power_id, manifest, source))
            print(f"WRAP: {destination.relative_to(ROOT)}")
    if "index" in spec:
        index = ROOT / spec["index"]
        write_generated_file(index, host_instruction_content(host))
        print(f"INDEX: {index.relative_to(ROOT)}")


def install_instruction_host(host: str) -> None:
    spec = HOST_SPECS[host]
    path = ROOT / spec["file"]
    write_generated_file(path, host_instruction_content(host))
    print(f"RULE: {path.relative_to(ROOT)}")
    if host == "kilo":
        config = ROOT / "kilo.jsonc"
        write_generated_file(config, kilo_config_content())
        print(f"CONFIG: {config.relative_to(ROOT)}")


def install_host_adapters(args: argparse.Namespace) -> int:
    selected = select_hosts(args.host)
    for host in selected:
        spec = HOST_SPECS[host]
        if spec["kind"] == "skills":
            install_skill_host(host, args.mode)
        else:
            install_instruction_host(host)
    return 0


def remove_host_adapters(host: str = "all") -> int:
    removed = 0
    for selected in select_hosts(host):
        for path in sorted(host_expected_paths(selected), reverse=True):
            target = path.parent if path.name == "SKILL.md" else path
            if target.exists() or target.is_symlink():
                if safe_remove_generated(target):
                    removed += 1
    return removed


def host_list(args: argparse.Namespace) -> int:
    rows = []
    for host in configured_hosts():
        spec = HOST_SPECS[host]
        rows.append(
            {
                "host": host,
                "kind": spec["kind"],
                "path": spec.get("root") or spec.get("file"),
            }
        )
    if args.json:
        emit(rows, as_json=True)
        return 0
    print(f"{'HOST':<10} {'KIND':<14} PATH")
    for row in rows:
        print(f"{row['host']:<10} {row['kind']:<14} {row['path']}")
    print("Aliases: bionics, biotic, ollama -> custom")
    return 0


def host_status(args: argparse.Namespace) -> int:
    failed = False
    for host in select_hosts(args.host):
        paths = host_expected_paths(host)
        for path in paths:
            state = "ready" if path.exists() else "missing"
            failed = failed or state == "missing"
            print(f"{host:<10} {path.relative_to(ROOT).as_posix():<58} {state}")
    return 1 if failed else 0


def provider_config_path(provider_id: str) -> Path:
    return ROOT / ".agents" / "providers" / f"{provider_id}.json"


def provider_env_path(provider_id: str) -> Path:
    return ROOT / ".agents" / "providers" / f"{provider_id}.env.example"


def provider_config(provider: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    model_env = str(provider.get("model_env", "OLLAMA_MODEL"))
    model = args.model or os.environ.get(model_env) or provider.get("default_model")
    if not model:
        raise DwError(f"provider {provider['id']} requires --model or {model_env}")
    base_url = args.base_url or provider.get("base_url")
    api_key = args.api_key or provider.get("api_key", "ollama")
    return {
        GENERATED_JSON_KEY: "dw",
        "provider": provider["id"],
        "protocol": provider.get("type", "openai-compatible"),
        "baseUrl": base_url,
        "apiKey": api_key,
        "model": model,
        "systemPrompt": ".agents/DW_AGENT.md",
    }


def write_provider_files(provider: dict[str, Any], config: dict[str, Any]) -> None:
    config_path = provider_config_path(provider["id"])
    if config_path.exists() and not is_generated_path(config_path):
        raise DwError(f"refusing to replace unmanaged provider config: {config_path.relative_to(ROOT)}")
    atomic_write(config_path, json.dumps(config, indent=2) + "\n")
    env_path = provider_env_path(provider["id"])
    env_content = (
        f"# {GENERATED_MARKER}\n"
        f"OLLAMA_BASE_URL={config['baseUrl']}\n"
        f"OLLAMA_API_KEY={config['apiKey']}\n"
        f"OLLAMA_MODEL={config['model']}\n"
    )
    write_generated_file(env_path, env_content)


def select_providers(provider_id: str) -> list[dict[str, Any]]:
    if provider_id == "all":
        return provider_entries()
    return [find_provider(provider_id)]


def provider_install(args: argparse.Namespace) -> int:
    for provider in select_providers(args.provider_id):
        config = provider_config(provider, args)
        write_provider_files(provider, config)
        print(
            f"PROVIDER: {provider['id']} model={config['model']} "
            f"base={config['baseUrl']}"
        )
    return 0


def load_provider_config(provider_id: str) -> dict[str, Any]:
    path = provider_config_path(provider_id)
    if not path.is_file():
        raise DwError(f"provider {provider_id} is not installed")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DwError(f"invalid provider config: {path.relative_to(ROOT)}")
    return data


def probe_openai_provider(config: dict[str, Any]) -> tuple[bool, str]:
    url = str(config["baseUrl"]).rstrip("/") + "/models"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {config.get('apiKey', 'ollama')}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200, f"HTTP {response.status}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, str(exc)


def provider_status(args: argparse.Namespace) -> int:
    failed = False
    for provider in select_providers(args.provider_id):
        path = provider_config_path(provider["id"])
        if not path.is_file():
            print(f"{provider['id']:<10} missing  {path.relative_to(ROOT)}")
            failed = True
            continue
        config = load_provider_config(provider["id"])
        state = "ready"
        detail = f"model={config.get('model')} base={config.get('baseUrl')}"
        if args.probe:
            ok, probe_detail = probe_openai_provider(config)
            state = "online" if ok else "offline"
            detail += f" probe={probe_detail}"
            failed = failed or not ok
        print(f"{provider['id']:<10} {state:<8} {detail}")
    return 1 if failed else 0


def provider_info(args: argparse.Namespace) -> int:
    config = load_provider_config(args.provider_id)
    if args.json:
        emit(config, as_json=True)
        return 0
    for key in ("provider", "protocol", "baseUrl", "model", "systemPrompt"):
        print(f"{key}: {config.get(key)}")
    return 0


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
    parser.add_argument("--version", action="version", version="dw 2.3")
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

    host_list_parser = host_commands.add_parser("list")
    host_list_parser.add_argument("--json", action="store_true")
    host_list_parser.set_defaults(handler=host_list)

    host_choices = [*HOST_SPECS, *HOST_ALIASES, "all"]
    host_install_parser = host_commands.add_parser("install")
    host_install_parser.add_argument("host", nargs="?", choices=host_choices, default="all")
    host_install_parser.add_argument(
        "--mode",
        choices=["wrapper", "link", "copy"],
        default="wrapper",
        help="used by skill-based hosts; wrapper is cross-platform",
    )
    host_install_parser.set_defaults(handler=install_host_adapters)

    host_status_parser = host_commands.add_parser("status")
    host_status_parser.add_argument("host", nargs="?", choices=host_choices, default="all")
    host_status_parser.set_defaults(handler=host_status)

    provider_parser = commands.add_parser("provider")
    provider_commands = provider_parser.add_subparsers(dest="provider_command", required=True)

    provider_install_parser = provider_commands.add_parser("install")
    provider_install_parser.add_argument("provider_id", nargs="?", default="all")
    provider_install_parser.add_argument("--model")
    provider_install_parser.add_argument("--base-url")
    provider_install_parser.add_argument("--api-key")
    provider_install_parser.set_defaults(handler=provider_install)

    provider_status_parser = provider_commands.add_parser("status")
    provider_status_parser.add_argument("provider_id", nargs="?", default="all")
    provider_status_parser.add_argument("--probe", action="store_true")
    provider_status_parser.set_defaults(handler=provider_status)

    provider_info_parser = provider_commands.add_parser("info")
    provider_info_parser.add_argument("provider_id")
    provider_info_parser.add_argument("--json", action="store_true")
    provider_info_parser.set_defaults(handler=provider_info)

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
