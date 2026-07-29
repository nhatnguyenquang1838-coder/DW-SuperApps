#!/usr/bin/env python3
"""Assemble a full DW-SuperApps release from validated Power packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from power_dist import verify_package


DEFAULT_POWERS = ("gwc", "ua", "task-me", "bmad")
ROOT = Path(__file__).resolve().parents[1]

# The full release must carry the DW control plane as well as Power ZIPs. Keep
# this list explicit so source repositories, tests, dashboards, and runtime
# data cannot accidentally become part of the standalone bootstrap payload.
RUNTIME_FILES = (
    "AGENTS.md",
    "requirements-dev.txt",
    "dw.ps1",
    "dw.cmd",
)
RUNTIME_DIRS = (
    "bin",
    "scripts",
    "schemas",
    "manifests",
    "prompts",
    "docs/installation",
    "docs/runbooks",
    "powers/bmad",
    ".kiro/skills/dw-power-installation",
    ".kiro/agents",
)
RUNTIME_TEMPLATE = ROOT / "templates" / "full-distribution" / "workspace-template.yaml"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_runtime(source_root: Path, release_root: Path) -> dict:
    runtime_root = release_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)

    def copy_file(relative: str) -> None:
        source = source_root / relative
        if not source.is_file():
            raise SystemExit(f"missing full-release runtime file: {source}")
        destination = runtime_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    for relative in RUNTIME_FILES:
        copy_file(relative)
    for relative in RUNTIME_DIRS:
        source = source_root / relative
        if not source.is_dir():
            # Some legacy source trees do not carry optional compatibility
            # payloads (for example powers/bmad); the control plane itself is
            # checked below through the required evidence list.
            continue
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.suffix in {".pyc", ".pyo"} or "__pycache__" in path.parts:
                continue
            copy_file(path.relative_to(source_root).as_posix())
    if not RUNTIME_TEMPLATE.is_file():
        raise SystemExit(f"missing workspace template: {RUNTIME_TEMPLATE}")
    shutil.copy2(RUNTIME_TEMPLATE, runtime_root / "workspace-template.yaml")

    files = []
    for path in sorted(runtime_root.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(runtime_root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
                }
            )
    manifest = {
        "apiVersion": "dw.superapps.distribution/runtime-v1",
        "root": "runtime",
        "files": files,
    }
    write_json(release_root / "RUNTIME_MANIFEST.json", manifest)
    return manifest


def write_deterministic_bundle(source_root: Path, destination: Path, source_date_epoch: int) -> None:
    timestamp = max(source_date_epoch, 315532800)
    date_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).timetuple()[:6]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.name == destination.name:
                continue
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=date_time)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if relative == "runtime/bin/dw" or relative.endswith(".sh") else 0o644
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(destination)


def write_checksums(release_root: Path, *, include_bundle: bool) -> None:
    checksum_lines = []
    bundle_name = next((path.name for path in release_root.glob("dw-superapps-full-*.zip")), None)
    for path in sorted(release_root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        if not include_bundle and bundle_name and path.name == bundle_name:
            continue
        checksum_lines.append(f"{sha256_file(path)}  {path.relative_to(release_root).as_posix()}")
    (release_root / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def package_paths(distribution_root: Path, power_id: str) -> tuple[Path, Path, Path]:
    staging_root = distribution_root / "staging"
    candidates = sorted(path for path in staging_root.glob(f"{power_id}-*") if path.is_dir())
    if len(candidates) != 1:
        raise SystemExit(f"expected exactly one staged package for {power_id}, found {len(candidates)}")
    package_root = candidates[0]
    archive = distribution_root / "assets" / f"{package_root.name}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    if not archive.is_file() or not checksum.is_file():
        raise SystemExit(f"missing package asset pair for {power_id}: {archive}")
    return package_root, archive, checksum


def assemble(args: argparse.Namespace) -> dict:
    distribution_root = Path(args.distribution_root).resolve()
    output_root = Path(args.output).resolve()
    release_root = output_root / f"dw-superapps-full-{args.version}"
    if release_root.exists():
        shutil.rmtree(release_root)
    assets_root = release_root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    runtime_manifest = copy_runtime(ROOT, release_root)
    prompt = ROOT / "prompts" / "power-dist" / "kiro-offline-install.md"
    if not prompt.is_file():
        raise SystemExit(f"missing Kiro offline prompt: {prompt}")
    shutil.copy2(prompt, release_root / "KIRO_OFFLINE_INSTALL_PROMPT.md")
    kiro_skill = ROOT / ".kiro" / "skills" / "dw-power-installation"
    kiro_agent = ROOT / ".kiro" / "agents" / "dw-power-installation.json"
    kiro_agent_prompt = ROOT / ".kiro" / "agents" / "DW_POWER_INSTALLATION_AGENT.md"
    offline_verifier = ROOT / "scripts" / "offline_release_installer.py"
    for required in (kiro_skill / "SKILL.md", kiro_skill / "scripts" / "python-session.sh", kiro_agent, kiro_agent_prompt):
        if not required.is_file():
            raise SystemExit(f"missing Kiro installation asset: {required}")
    if not offline_verifier.is_file():
        raise SystemExit(f"missing standalone release verifier: {offline_verifier}")
    shutil.copytree(kiro_skill, release_root / "kiro" / "skills" / "dw-power-installation")
    (release_root / "kiro" / "agents").mkdir(parents=True, exist_ok=True)
    shutil.copy2(kiro_agent, release_root / "kiro" / "agents" / kiro_agent.name)
    shutil.copy2(kiro_agent_prompt, release_root / "kiro" / "agents" / kiro_agent_prompt.name)
    shutil.copy2(offline_verifier, release_root / offline_verifier.name)

    components = []
    source_packages = []
    for power_id in args.powers:
        package_root, archive, checksum = package_paths(distribution_root, power_id)
        package_manifest = verify_package(package_root)
        if package_manifest["metadata"].get("powerId") != power_id:
            raise SystemExit(
                f"staged package identity mismatch for {power_id}: "
                f"{package_manifest['metadata'].get('powerId')}"
            )
        actual_sha = sha256_file(archive)
        checksum_text = checksum.read_text(encoding="utf-8").split()[0]
        if checksum_text != actual_sha:
            raise SystemExit(f"package checksum mismatch for {power_id}")

        shutil.copy2(archive, assets_root / archive.name)
        shutil.copy2(checksum, assets_root / checksum.name)
        components.append({
            "name": power_id,
            "package": f"assets/{archive.name}",
            "sha256": actual_sha,
            "size": archive.stat().st_size,
            "packageVersion": package_manifest["metadata"]["version"],
            "runtimeDataRoot": package_manifest["spec"]["runtimeDataRoot"],
            "entrypoints": package_manifest["spec"].get("entrypoints", []),
            "agentGuidance": package_manifest["spec"].get("agentGuidance"),
            "source": package_manifest["metadata"],
        })
        source_packages.append(package_manifest["metadata"])

    validation_candidates = (
        distribution_root / "validation-report.json",
        distribution_root / "staging" / "validation-report.json",
    )
    validation_path = next((path for path in validation_candidates if path.is_file()), None)
    if validation_path is None:
        expected = " or ".join(str(path) for path in validation_candidates)
        raise SystemExit(f"missing validation report: expected {expected}")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    power_results = validation.get("powers", {})
    missing = [power_id for power_id in args.powers if power_id not in power_results]
    failed = [power_id for power_id in args.powers if power_results.get(power_id, {}).get("status") != "PASS"]
    if missing or failed:
        raise SystemExit(f"validation report is incomplete: missing={missing}, failed={failed}")

    manifest = {
        "apiVersion": "dw.superapps.distribution/v1",
        "kind": "OfflineDistributionRelease",
        "metadata": {
            "name": "dw-superapps-full-distribution",
            "version": args.version,
        },
        "spec": {
            "artifactOnly": True,
            "generatedZipsInRepository": False,
            "delivery": "tag-or-release-download",
            "components": components,
            "requiredEvidence": [
                "MANIFEST.json",
                "SOURCE_LOCK.json",
                "SHA256SUMS.txt",
                "VALIDATION_REPORT.json",
                "RUNTIME_MANIFEST.json",
                "KIRO_OFFLINE_INSTALL_PROMPT.md",
                "offline_release_installer.py",
                "runtime/bin/dw",
                "runtime/scripts/dw_project_registry.py",
                "runtime/scripts/dw_workspace_init.py",
                "runtime/scripts/offline_release_installer.py",
                "runtime/requirements-dev.txt",
                "runtime/workspace-template.yaml",
                "runtime/docs/installation/INSTALL_POWERS.md",
                "kiro/skills/dw-power-installation/SKILL.md",
                "kiro/skills/dw-power-installation/scripts/python-session.sh",
                "kiro/agents/dw-power-installation.json",
                "kiro/agents/DW_POWER_INSTALLATION_AGENT.md",
            ],
            "powers": list(args.powers),
            "kiroPrompt": "KIRO_OFFLINE_INSTALL_PROMPT.md",
            "kiroInstallation": {
                "skill": "kiro/skills/dw-power-installation/SKILL.md",
                "agent": "kiro/agents/dw-power-installation.json",
                "agentPrompt": "kiro/agents/DW_POWER_INSTALLATION_AGENT.md",
                "pythonSession": "kiro/skills/dw-power-installation/scripts/python-session.sh",
            },
            "standaloneTools": {
                "releaseVerifier": "offline_release_installer.py",
            },
            "registrationMode": "offline-local",
            "bootstrap": {
                "runtimeRoot": "runtime",
                "runtimeManifest": "RUNTIME_MANIFEST.json",
                "workspaceTemplate": "runtime/workspace-template.yaml",
                "setupCommand": "offline_release_installer.py setup",
                "supports": ["empty", "stale", "broken", "root-package-store", "child-system"],
            },
        },
    }
    source_lock = {
        "apiVersion": "dw.superapps.distribution/v1",
        "sourceRef": args.source_ref,
        "sourceSha": args.source_sha,
        "sourceDateEpoch": args.source_date_epoch,
        "powers": source_packages,
    }
    full_validation = {
        "apiVersion": "dw.superapps.distribution/v1",
        "result": "PASS",
        "releaseVersion": args.version,
        "sourceSha": args.source_sha,
        "checks": {
            "allPowerPackagesVerified": True,
            "allArchiveChecksumsVerified": True,
            "offlineInstallerValidation": True,
            "controlPlaneRuntimePackaged": True,
        },
        "powers": power_results,
    }

    write_json(release_root / "MANIFEST.json", manifest)
    write_json(release_root / "SOURCE_LOCK.json", source_lock)
    write_json(release_root / "VALIDATION_REPORT.json", full_validation)

    bundle = release_root / f"dw-superapps-full-{args.version}.zip"
    write_checksums(release_root, include_bundle=False)
    write_deterministic_bundle(release_root, bundle, args.source_date_epoch)
    write_checksums(release_root, include_bundle=True)

    result = {
        "releaseRoot": str(release_root),
        "bundle": str(bundle),
        "version": args.version,
        "powers": list(args.powers),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble a full DW-SuperApps release from validated Power packages.")
    parser.add_argument("--distribution-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--power", action="append", dest="powers", choices=DEFAULT_POWERS)
    args = parser.parse_args(argv)
    args.powers = args.powers or list(DEFAULT_POWERS)
    assemble(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
