from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    ROOT,
    ConsumerError,
    distribution_roots,
    installed_root,
    load_json,
    load_yaml,
    manifest,
)
from .package_io import verify_installed_manifest, verify_package

LOCK_PATH = ROOT / "manifests" / "power-compatibility-lock.json"


def compatibility_lock() -> dict[str, Any]:
    data = load_json(LOCK_PATH)
    if data.get("schemaVersion") != "1.0" or not isinstance(data.get("powers"), dict):
        raise ConsumerError("invalid Power compatibility lock")
    return data


def validate_lock(manifests: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    lock = compatibility_lock()
    manifests = manifests or {
        power_id: manifest(power_id) for power_id in sorted(lock["powers"])
    }
    errors: list[str] = []
    warnings: list[str] = []
    if set(manifests) != set(lock["powers"]):
        errors.append(
            "compatibility lock Power IDs differ from manifests: "
            f"lock={sorted(lock['powers'])} manifests={sorted(manifests)}"
        )
    for power_id, record in sorted(lock["powers"].items()):
        data = manifests.get(power_id)
        if not data:
            continue
        spec = data["spec"]
        distribution = spec.get("distribution") or {}
        state = distribution.get("providerState") or {}
        mode = (distribution.get("modes") or {}).get("powerDist") or {}
        checks = {
            "sourceRepository": spec.get("source"),
            "distributionRepository": mode.get("repository"),
            "distributionRef": mode.get("ref"),
            "publishedSourceSha": state.get("sourceCommit"),
            "packageVersion": data.get("metadata", {}).get("version"),
            "runtimeDataRoot": spec.get("runtimeDataRoot"),
        }
        for field, actual in checks.items():
            if record.get(field) != actual:
                errors.append(
                    f"{power_id} compatibility {field} mismatch: "
                    f"lock={record.get(field)!r} manifest={actual!r}"
                )
        skill_entrypoints = [
            item for item in record.get("entrypoints", []) if item.endswith("SKILL.md")
        ]
        candidates = set((spec.get("entrypoints") or {}).get("skillCandidates") or [])
        missing = sorted(set(skill_entrypoints) - candidates)
        if missing:
            errors.append(f"{power_id} manifest omits published skill entrypoints: {missing}")
        expected_status = (
            "CURRENT"
            if record.get("providerHeadSha") == record.get("publishedSourceSha")
            else "PROVIDER_SOURCE_AHEAD"
        )
        if record.get("status") != expected_status:
            errors.append(
                f"{power_id} compatibility status must be {expected_status}, "
                f"found {record.get('status')}"
            )
        if expected_status == "PROVIDER_SOURCE_AHEAD":
            warnings.append(
                f"{power_id}: provider main {record['providerHeadSha']} is ahead of "
                f"published distribution {record['publishedSourceSha']}"
            )
    if errors:
        raise ConsumerError("Power compatibility lock validation failed:\n- " + "\n- ".join(errors))
    return {
        "status": "PASS_WITH_WARNINGS" if warnings else "PASS",
        "checked_at": lock.get("checkedAt"),
        "power_count": len(lock["powers"]),
        "warnings": warnings,
    }


def _package_metadata(package_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    package_manifest = load_json(package_root / "MANIFEST.json")
    source = load_json(package_root / "SOURCE.json") if (package_root / "SOURCE.json").is_file() else {}
    power = load_yaml(package_root / "POWER.yaml") if (package_root / "POWER.yaml").is_file() else {}
    return package_manifest, source, power


def sanity(args: Any) -> dict[str, Any]:
    roots = distribution_roots(getattr(args, "store_root", None))
    install = installed_root(roots, args.power_id)
    if not install.is_dir():
        raise ConsumerError(f"Power is not installed in workspace store: {install}")
    package_manifest = verify_package(install, args.power_id)
    verify_installed_manifest(install, package_manifest)
    package_manifest, source, power = _package_metadata(install)
    record = compatibility_lock()["powers"].get(args.power_id)
    if not record:
        raise ConsumerError(f"Power is not registered in compatibility lock: {args.power_id}")

    mismatches: list[str] = []
    warnings: list[str] = []
    metadata = package_manifest.get("metadata") or {}
    spec = package_manifest.get("spec") or {}
    comparisons = {
        "packageVersion": metadata.get("version"),
        "publishedSourceSha": source.get("sha") or metadata.get("sourceSha"),
        "sourceRepository": source.get("repository") or metadata.get("sourceRepository"),
        "runtimeDataRoot": spec.get("runtimeDataRoot"),
        "entrypoints": spec.get("entrypoints"),
    }
    for field, actual in comparisons.items():
        expected = record.get(field)
        if actual != expected:
            mismatches.append(f"{field}: expected {expected!r}, found {actual!r}")

    if power:
        power_metadata = power.get("metadata") or {}
        power_spec = power.get("spec") or {}
        if power_metadata.get("id") != args.power_id:
            mismatches.append("POWER.yaml identity mismatch")
        if power_metadata.get("version") != metadata.get("version"):
            mismatches.append("POWER.yaml version differs from MANIFEST.json")
        if power_spec.get("runtimeDataRoot") != spec.get("runtimeDataRoot"):
            mismatches.append("POWER.yaml runtimeDataRoot differs from MANIFEST.json")
        if power_spec.get("entrypoints") != spec.get("entrypoints"):
            mismatches.append("POWER.yaml entrypoints differ from MANIFEST.json")
    else:
        warnings.append("legacy package has no POWER.yaml")

    guidance = spec.get("agentGuidance")
    if guidance:
        if not (install / guidance).is_file():
            mismatches.append(f"declared agent guidance is missing: {guidance}")
    else:
        warnings.append("legacy package has no declared agent guidance")

    if record.get("status") == "PROVIDER_SOURCE_AHEAD":
        warnings.append(
            f"provider source {record['providerHeadSha']} is ahead of published distribution "
            f"{record['publishedSourceSha']}"
        )
    if mismatches and (getattr(args, "strict", False) or getattr(args, "strict_compatibility", False)):
        raise ConsumerError("Power compatibility mismatch:\n- " + "\n- ".join(mismatches))
    warnings.extend(mismatches)
    return {
        "status": "PASS_WITH_WARNINGS" if warnings else "PASS",
        "power_id": args.power_id,
        "install_root": str(install),
        "package_version": metadata.get("version"),
        "source_sha": source.get("sha") or metadata.get("sourceSha"),
        "guidance": guidance or "legacy-embedded",
        "warnings": warnings,
    }
