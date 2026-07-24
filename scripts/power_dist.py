#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECIPE_SCHEMA = ROOT / "schemas" / "power-distribution.schema.json"
DEFAULT_MANIFEST_SCHEMA = ROOT / "schemas" / "power-package-manifest.schema.json"
DEFAULT_RUNTIME_TEMPLATES = ROOT / "templates" / "power-runtime"

DEFAULT_FORBIDDEN_PATTERNS = (
    ".git/**",
    "**/.git/**",
    ".gwc/**",
    "**/.gwc/**",
    ".ua/**",
    "**/.ua/**",
    ".task-me/**",
    "**/.task-me/**",
    "node_modules/**",
    "**/node_modules/**",
    "__pycache__/**",
    "**/__pycache__/**",
    ".pytest_cache/**",
    "**/.pytest_cache/**",
    ".mypy_cache/**",
    "**/.mypy_cache/**",
    ".ruff_cache/**",
    "**/.ruff_cache/**",
    "dashboard/**",
    "**/dashboard/**",
    "dashboards/**",
    "**/dashboards/**",
    "frontend/**",
    "**/frontend/**",
    "web-ui/**",
    "**/web-ui/**",
    "plans/**",
    "**/plans/**",
    "task-plans/**",
    "**/task-plans/**",
    "tasks/**",
    "**/tasks/**",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "secrets/**",
    "**/secrets/**",
    "credentials/**",
    "**/credentials/**",
    "id_rsa",
    "**/id_rsa",
    "id_ed25519",
    "**/id_ed25519",
)
DEFAULT_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
)
MAX_SECRET_SCAN_BYTES = 2_000_000
GENERATED_FILES = ("POWER.yaml", "SOURCE.json", "VERSION")


class DistributionError(RuntimeError):
    pass


def load_structured(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DistributionError(f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise DistributionError(f"expected an object at {path}")
    return data


def validate_document(document: dict[str, Any], schema_path: Path) -> None:
    schema = load_structured(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        rendered = []
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            rendered.append(f"{location}: {error.message}")
        raise DistributionError("schema validation failed:\n- " + "\n- ".join(rendered))


def validate_recipe(recipe: dict[str, Any], schema_path: Path = DEFAULT_RECIPE_SCHEMA) -> None:
    validate_document(recipe, schema_path)
    for field in ("include", "exclude"):
        for pattern in recipe["spec"].get(field, []):
            ensure_relative(pattern, label=f"spec.{field}")
    for pattern in recipe["spec"].get("forbidden", {}).get("paths", []):
        ensure_relative(pattern, label="spec.forbidden.paths")
    for path in recipe["spec"]["package"]["entrypoints"]:
        ensure_relative(path, label="spec.package.entrypoints")
    ensure_relative(recipe["spec"]["runtime"]["dataRoot"], label="spec.runtime.dataRoot")


def ensure_relative(value: str, *, label: str) -> str:
    normalized = value.replace("\\", "/")
    if "\x00" in normalized:
        raise DistributionError(f"{label} contains a NUL byte: {value!r}")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise DistributionError(f"{label} must be relative: {value}")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise DistributionError(f"{label} may not traverse parents: {value}")
    if not parts:
        raise DistributionError(f"{label} may not be empty")
    return normalized


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def matches(path: str, pattern: str) -> bool:
    normalized = path.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    return candidate.match(pattern) or fnmatch.fnmatchcase(normalized, pattern)


def _iter_included(source_root: Path, patterns: Iterable[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in patterns:
        normalized = ensure_relative(pattern, label="include pattern")
        for match in source_root.glob(normalized):
            if match.is_symlink():
                raise DistributionError(f"symlinks are not distributable: {match}")
            if match.is_dir():
                children = sorted(match.rglob("*"))
            else:
                children = [match]
            for child in children:
                if child.is_symlink():
                    raise DistributionError(f"symlinks are not distributable: {child}")
                if child.is_file() and child not in seen:
                    seen.add(child)
                    yield child


def _forbidden_patterns(recipe: dict[str, Any]) -> tuple[str, ...]:
    runtime_root = recipe["spec"]["runtime"]["dataRoot"].rstrip("/")
    runtime_patterns = (runtime_root, f"{runtime_root}/**")
    custom = tuple(recipe["spec"].get("forbidden", {}).get("paths", []))
    return DEFAULT_FORBIDDEN_PATTERNS + runtime_patterns + custom


def _scan_secret_content(path: Path, custom_patterns: Iterable[str]) -> None:
    if path.stat().st_size > MAX_SECRET_SCAN_BYTES:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    patterns = list(DEFAULT_SECRET_PATTERNS)
    for pattern in custom_patterns:
        try:
            patterns.append(re.compile(pattern))
        except re.error as exc:
            raise DistributionError(f"invalid forbidden content pattern {pattern!r}: {exc}") from exc
    for pattern in patterns:
        if pattern.search(text):
            raise DistributionError(f"forbidden secret-like content in {path}: {pattern.pattern}")


def collect_files(recipe: dict[str, Any], source_root: Path) -> list[Path]:
    source_root = source_root.resolve()
    excludes = tuple(recipe["spec"].get("exclude", []))
    forbidden = _forbidden_patterns(recipe)
    custom_content = recipe["spec"].get("forbidden", {}).get("contentPatterns", [])
    selected: list[Path] = []
    collisions: dict[str, str] = {}

    for path in _iter_included(source_root, recipe["spec"]["include"]):
        resolved = path.resolve(strict=True)
        if not is_within(resolved, source_root):
            raise DistributionError(f"included file escapes source root: {path}")
        relative = resolved.relative_to(source_root).as_posix()
        if any(matches(relative, pattern) for pattern in excludes):
            continue
        hit = next((pattern for pattern in forbidden if matches(relative, pattern)), None)
        if hit:
            raise DistributionError(f"forbidden path included: {relative} (matched {hit})")
        key = relative.casefold()
        previous = collisions.get(key)
        if previous and previous != relative:
            raise DistributionError(f"case-colliding paths: {previous} and {relative}")
        collisions[key] = relative
        _scan_secret_content(resolved, custom_content)
        selected.append(resolved)

    if not selected:
        raise DistributionError("recipe selected no files")

    selected.sort(key=lambda path: path.relative_to(source_root).as_posix())
    entrypoints = recipe["spec"]["package"]["entrypoints"]
    selected_paths = {path.relative_to(source_root).as_posix() for path in selected}
    missing = [path for path in entrypoints if path not in selected_paths]
    if missing:
        raise DistributionError(f"entrypoints missing from selected files: {', '.join(missing)}")
    return selected


def atomic_write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs: dict[str, Any] = {}
    if mode == "w":
        kwargs["encoding"] = "utf-8"
        kwargs["newline"] = "\n"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode, dir=path.parent, delete=False, **kwargs) as handle:
            handle.write(content)
            temporary = handle.name
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_runtime_templates(staging_root: Path, templates_root: Path) -> None:
    if not templates_root.is_dir():
        raise DistributionError(f"runtime templates not found: {templates_root}")
    for source in sorted(templates_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(templates_root)
        destination = staging_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        mode = 0o755 if relative.parts and relative.parts[0] == "bin" else 0o644
        destination.chmod(mode)


def package_metadata(
    recipe: dict[str, Any],
    *,
    version: str,
    source_repository: str,
    source_ref: str,
    source_sha: str,
    source_date_epoch: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = recipe["metadata"]
    spec = recipe["spec"]
    power = {
        "apiVersion": "dw.superapps/v1",
        "kind": "PowerPackage",
        "metadata": {
            "id": metadata["id"],
            "name": metadata["name"],
            "version": version,
            "description": metadata.get("description", ""),
        },
        "spec": {
            "entrypoints": spec["package"]["entrypoints"],
            "managedPaths": spec["package"].get("managedPaths", []),
            "runtimeDataRoot": spec["runtime"]["dataRoot"],
            "configRequired": spec["runtime"].get("configRequired", False),
        },
    }
    source = {
        "repository": source_repository,
        "ref": source_ref,
        "sha": source_sha,
        "sourceDateEpoch": source_date_epoch,
        "recipeApiVersion": recipe["apiVersion"],
    }
    return power, source


def build_manifest(
    recipe: dict[str, Any],
    staging_root: Path,
    *,
    version: str,
    source_repository: str,
    source_ref: str,
    source_sha: str,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(staging_root.rglob("*")):
        if not path.is_file() or path.name == "MANIFEST.json":
            continue
        relative = path.relative_to(staging_root).as_posix()
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
            }
        )
    return {
        "apiVersion": "dw.superapps/v1",
        "kind": "PowerPackageManifest",
        "metadata": {
            "powerId": recipe["metadata"]["id"],
            "version": version,
            "sourceSha": source_sha,
            "sourceRepository": source_repository,
            "sourceRef": source_ref,
        },
        "spec": {
            "entrypoints": recipe["spec"]["package"]["entrypoints"],
            "runtimeDataRoot": recipe["spec"]["runtime"]["dataRoot"],
            "managedPaths": recipe["spec"]["package"].get("managedPaths", []),
            "generatedFiles": list(GENERATED_FILES),
        },
        "files": files,
    }


def build_staging_tree(
    recipe: dict[str, Any],
    source_root: Path,
    staging_root: Path,
    *,
    version: str,
    source_repository: str,
    source_ref: str,
    source_sha: str,
    source_date_epoch: int = 0,
    templates_root: Path = DEFAULT_RUNTIME_TEMPLATES,
) -> Path:
    validate_recipe(recipe)
    source_root = source_root.resolve()
    staging_root = staging_root.resolve()
    if staging_root == source_root or is_within(staging_root, source_root):
        raise DistributionError("staging root must be outside the source root")
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)

    for source in collect_files(recipe, source_root):
        relative = source.relative_to(source_root)
        destination = staging_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if os.access(source, os.X_OK) else 0o644)

    if recipe["spec"]["package"].get("runtimeTemplates", True):
        copy_runtime_templates(staging_root, templates_root)

    power, source = package_metadata(
        recipe,
        version=version,
        source_repository=source_repository,
        source_ref=source_ref,
        source_sha=source_sha,
        source_date_epoch=source_date_epoch,
    )
    atomic_write(staging_root / "POWER.yaml", yaml.safe_dump(power, sort_keys=False))
    atomic_write(staging_root / "SOURCE.json", json.dumps(source, indent=2, sort_keys=True) + "\n")
    atomic_write(staging_root / "VERSION", version + "\n")

    manifest = build_manifest(
        recipe,
        staging_root,
        version=version,
        source_repository=source_repository,
        source_ref=source_ref,
        source_sha=source_sha,
    )
    validate_document(manifest, DEFAULT_MANIFEST_SCHEMA)
    atomic_write(staging_root / "MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify_package(staging_root)
    return staging_root


def zip_timestamp(source_date_epoch: int) -> tuple[int, int, int, int, int, int]:
    safe_epoch = max(source_date_epoch, 315532800)
    value = datetime.fromtimestamp(safe_epoch, tz=timezone.utc)
    return (value.year, value.month, value.day, value.hour, value.minute, value.second)


def create_deterministic_zip(
    staging_root: Path,
    archive_path: Path,
    *,
    package_directory: str,
    source_date_epoch: int = 0,
) -> Path:
    package_directory = ensure_relative(package_directory, label="package directory").rstrip("/")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    timestamp = zip_timestamp(source_date_epoch)
    with zipfile.ZipFile(
        temporary,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path in sorted(staging_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(staging_root).as_posix()
            info = zipfile.ZipInfo(f"{package_directory}/{relative}", date_time=timestamp)
            mode = stat.S_IMODE(path.stat().st_mode)
            info.external_attr = (mode & 0xFFFF) << 16
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as handle:
                archive.writestr(info, handle.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(temporary, archive_path)
    return archive_path


def verify_package(package_root: Path) -> dict[str, Any]:
    package_root = package_root.resolve()
    manifest_path = package_root / "MANIFEST.json"
    manifest = load_structured(manifest_path)
    validate_document(manifest, DEFAULT_MANIFEST_SCHEMA)

    expected = {entry["path"]: entry for entry in manifest["files"]}
    actual = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if set(expected) != actual:
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise DistributionError(f"manifest file set mismatch; missing={missing}, extra={extra}")

    for relative, entry in expected.items():
        path = package_root / relative
        if path.stat().st_size != entry["size"]:
            raise DistributionError(f"size mismatch: {relative}")
        if sha256_file(path) != entry["sha256"]:
            raise DistributionError(f"hash mismatch: {relative}")

    for entrypoint in manifest["spec"]["entrypoints"]:
        if entrypoint not in expected:
            raise DistributionError(f"manifest entrypoint missing: {entrypoint}")

    return manifest


def build_command(args: argparse.Namespace) -> dict[str, str]:
    recipe_path = Path(args.recipe).resolve()
    recipe = load_structured(recipe_path)
    validate_recipe(recipe)
    output_root = Path(args.output).resolve()
    power_id = recipe["metadata"]["id"]
    directory_name = f"{power_id}-{args.version}"
    staging_root = output_root / "staging" / directory_name
    assets_root = output_root / "assets"
    archive_path = assets_root / f"{directory_name}.zip"
    checksum_path = assets_root / f"{directory_name}.zip.sha256"

    build_staging_tree(
        recipe,
        Path(args.source),
        staging_root,
        version=args.version,
        source_repository=args.source_repository or recipe["spec"]["source"]["repository"],
        source_ref=args.source_ref,
        source_sha=args.source_sha,
        source_date_epoch=args.source_date_epoch,
        templates_root=Path(args.templates_root),
    )
    create_deterministic_zip(
        staging_root,
        archive_path,
        package_directory=directory_name,
        source_date_epoch=args.source_date_epoch,
    )
    digest = sha256_file(archive_path)
    atomic_write(checksum_path, f"{digest}  {archive_path.name}\n")
    result = {
        "power_id": power_id,
        "version": args.version,
        "staging_root": str(staging_root),
        "archive": str(archive_path),
        "checksum": str(checksum_path),
        "sha256": digest,
    }
    print(json.dumps(result, sort_keys=True))
    return result


def verify_command(args: argparse.Namespace) -> None:
    manifest = verify_package(Path(args.package_root))
    print(
        json.dumps(
            {
                "status": "PASS",
                "power_id": manifest["metadata"]["powerId"],
                "version": manifest["metadata"]["version"],
                "files": len(manifest["files"]),
            },
            sort_keys=True,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic DW Power distributions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-recipe", help="Validate a distribution recipe.")
    validate_parser.add_argument("--recipe", required=True)
    validate_parser.set_defaults(
        handler=lambda args: (
            validate_recipe(load_structured(Path(args.recipe))),
            print(json.dumps({"status": "PASS", "recipe": str(Path(args.recipe))})),
        )
    )

    build_parser_ = subparsers.add_parser("build", help="Build a staged package and deterministic ZIP.")
    build_parser_.add_argument("--recipe", required=True)
    build_parser_.add_argument("--source", required=True)
    build_parser_.add_argument("--output", required=True)
    build_parser_.add_argument("--version", required=True)
    build_parser_.add_argument("--source-repository")
    build_parser_.add_argument("--source-ref", default="main")
    build_parser_.add_argument("--source-sha", required=True)
    build_parser_.add_argument("--source-date-epoch", type=int, default=0)
    build_parser_.add_argument("--templates-root", default=str(DEFAULT_RUNTIME_TEMPLATES))
    build_parser_.set_defaults(handler=build_command)

    verify_parser = subparsers.add_parser("verify", help="Verify a staged or installed package.")
    verify_parser.add_argument("--package-root", required=True)
    verify_parser.set_defaults(handler=verify_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
        return 0
    except (DistributionError, jsonschema.ValidationError, OSError, ValueError) as exc:
        print(f"power-dist: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
