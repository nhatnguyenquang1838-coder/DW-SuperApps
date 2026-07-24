#!/usr/bin/env python3
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
from pathlib import Path
from typing import Any

HOST_MAP = {
    "kiro": "kiro",
    "codex": "codex",
    "copilot": "github-copilot",
    "cline": "cline",
    "kilo": "kilo",
    "claude": "claude-code",
    "custom": "codex",
}
MIN_NODE = (20, 12, 0)


class BootstrapError(RuntimeError):
    pass


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise BootstrapError(detail or f"command failed: {' '.join(command)}")
    return result


def executable(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise BootstrapError(f"required executable not found: {name}")
    return value


def node_version(node: str) -> tuple[int, int, int]:
    value = run([node, "--version"], capture=True).stdout.strip().lstrip("v")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise BootstrapError(f"cannot parse Node.js version: {value}")
    return tuple(int(part) for part in match.groups())


def validate_package(root: Path) -> dict[str, Any]:
    required = [
        "package.json",
        "package-lock.json",
        "bmad-modules.yaml",
        "src/core-skills/module.yaml",
        "src/bmm-skills/module.yaml",
        "tools/installer/bmad-cli.js",
        "tools/installer/commands/install.js",
        "distribution/skills/bmad/SKILL.md",
    ]
    missing = [path for path in required if not (root / path).is_file()]
    if missing:
        raise BootstrapError("package is incomplete: " + ", ".join(missing))
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    return {
        "name": package.get("name"),
        "version": package.get("version"),
        "requiredFiles": len(required),
    }


def dependency_cache(root: Path, target: Path, npm: str, *, refresh: bool) -> Path:
    cache = target / ".dw" / "cache" / "bmad" / "npm"
    package_hash = sha256(root / "package-lock.json")
    marker = cache / ".lock-sha256"
    if refresh or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != package_hash:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix="bmad-npm-", dir=cache.parent))
        try:
            shutil.copyfile(root / "package.json", temporary / "package.json")
            shutil.copyfile(root / "package-lock.json", temporary / "package-lock.json")
            run(
                [
                    npm,
                    "ci",
                    "--omit=dev",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                ],
                cwd=temporary,
            )
            (temporary / ".lock-sha256").write_text(package_hash + "\n", encoding="utf-8")
            old = cache.parent / f".npm-old-{int(time.time())}"
            if cache.exists():
                os.replace(cache, old)
            else:
                old = None
            os.replace(temporary, cache)
            if old:
                shutil.rmtree(old)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    return cache


def safe_target(root: Path, target: Path) -> None:
    root = root.resolve()
    target = target.resolve()
    if root == target or root in target.parents or target in root.parents:
        raise BootstrapError("package root and consumer target must not contain each other")


def bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    root = package_root()
    target = Path(args.target).resolve()
    safe_target(root, target)
    package = validate_package(root)
    node = executable("node")
    npm = executable("npm")
    version = node_version(node)
    if version < MIN_NODE:
        raise BootstrapError(
            f"Node.js >= {'.'.join(map(str, MIN_NODE))} is required; found {'.'.join(map(str, version))}"
        )
    target.mkdir(parents=True, exist_ok=True)
    platform = HOST_MAP[args.host]

    result: dict[str, Any] = {
        "status": "READY" if args.check else "BOOTSTRAPPED",
        "package": package,
        "source": json.loads((root / "SOURCE.json").read_text(encoding="utf-8"))
        if (root / "SOURCE.json").is_file()
        else None,
        "target": str(target),
        "host": args.host,
        "platform": platform,
        "nodeVersion": ".".join(map(str, version)),
    }
    if args.check:
        return result

    cache = dependency_cache(root, target, npm, refresh=args.refresh_dependencies)
    command = [
        node,
        str(root / "tools" / "installer" / "bmad-cli.js"),
        "install",
        "--directory",
        str(target),
        "--modules",
        args.modules,
        "--tools",
        platform,
        "--yes",
        "--user-name",
        args.user_name,
        "--communication-language",
        args.communication_language,
        "--document-output-language",
        args.document_output_language,
        "--output-folder",
        args.output_folder,
    ]
    if (target / "_bmad").exists():
        command.extend(["--action", "update"])
    if args.project_knowledge:
        command.extend(["--set", f"bmm.project_knowledge={args.project_knowledge}"])

    env = dict(os.environ)
    node_path = cache / "node_modules"
    env["NODE_PATH"] = str(node_path) + (
        os.pathsep + env["NODE_PATH"] if env.get("NODE_PATH") else ""
    )
    env["NO_UPDATE_NOTIFIER"] = "1"
    run(command, cwd=root, env=env)

    marker = target / ".dw" / "bmad-bootstrap.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "managedBy": "dw-bmad-power",
                "packageVersion": package.get("version"),
                "sourceCommit": (result.get("source") or {}).get("sha"),
                "host": args.host,
                "platform": platform,
                "installedAtEpoch": int(time.time()),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result["marker"] = str(marker)
    result["dependencyCache"] = str(cache)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Bootstrap pinned BMAD Method sources into a consumer project.")
    result.add_argument("--target", required=True)
    result.add_argument("--host", choices=sorted(HOST_MAP), default="codex")
    result.add_argument("--modules", default="bmm")
    result.add_argument("--user-name", default="BMad")
    result.add_argument("--communication-language", default="English")
    result.add_argument("--document-output-language", default="English")
    result.add_argument("--output-folder", default="_bmad-output")
    result.add_argument("--project-knowledge", default="docs")
    result.add_argument("--refresh-dependencies", action="store_true")
    result.add_argument("--check", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        print(json.dumps(bootstrap(args), indent=2, sort_keys=True))
        return 0
    except (BootstrapError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"bmad-bootstrap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
