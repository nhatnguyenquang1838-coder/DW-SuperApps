"""Exact-source standards resolution for the TaskController session boundary.

The resolver is deliberately pure at the TaskController boundary: callers provide
an exact-source reader, and this module verifies the returned bytes before exposing
only the declared engineering/policy instructions as immutable session context.
It does not fetch providers, mutate the repository, invoke an Analyzer, or persist
session state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Protocol, Sequence

from taskcontroller.errors import TaskControllerValidationError


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
STANDARDS_RESOLUTION_BLOCKED = "STANDARDS_RESOLUTION_BLOCKED"


class StandardsResolutionError(TaskControllerValidationError):
    """Stable local error for an invalid or unverifiable standards profile."""

    def __init__(
        self, code: str, message: str, *, reason_code: str | None = None
    ) -> None:
        self.code = code
        self.reason_code = reason_code or code
        super().__init__(f"{code}: {message}")


class StandardsResolutionBlocked(StandardsResolutionError):
    """Required standards could not be reproduced, so analysis must not start."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(
            STANDARDS_RESOLUTION_BLOCKED,
            message,
            reason_code=reason_code,
        )


def _canonical_digest(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StandardsResolutionError(
            "STANDARDS_PROFILE_INVALID", f"profile is not canonical JSON: {exc}"
        ) from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise StandardsResolutionError(
            "STANDARDS_PROFILE_INVALID", f"{field} must be a stable non-empty identifier"
        )
    return value


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise StandardsResolutionError(
            "STANDARDS_PROFILE_INVALID", f"{field} must be sha256:<64 lowercase hex>"
        )
    return value


@dataclass(frozen=True)
class StandardsSourceRef:
    """One immutable repository/commit/path/content-digest binding."""

    repository: str
    commit_sha: str
    path: str
    blob_digest: str

    def __post_init__(self) -> None:
        _require_id(self.repository, "repository")
        if not isinstance(self.commit_sha, str) or not _COMMIT_RE.fullmatch(self.commit_sha):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID",
                "commit_sha must be an exact 40- or 64-character lowercase commit ID",
            )
        if (
            not isinstance(self.path, str)
            or not self.path
            or self.path.startswith("/")
            or "\\" in self.path
            or "\x00" in self.path
            or any(part in {"", ".", ".."} for part in self.path.split("/"))
        ):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "source path must be a safe relative repository path"
            )
        _require_digest(self.blob_digest, "blob_digest")

    def to_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "path": self.path,
            "blob_digest": self.blob_digest,
        }

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.repository, self.commit_sha, self.path, self.blob_digest)


@dataclass(frozen=True)
class StandardsProfile:
    """A digest-bound set of exact standards sources."""

    profile_id: str
    version: str
    digest: str
    sources: tuple[StandardsSourceRef, ...]

    def __post_init__(self) -> None:
        _require_id(self.profile_id, "profile_id")
        _require_id(self.version, "version")
        _require_digest(self.digest, "digest")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "profile must declare at least one source"
            )
        if any(not isinstance(source, StandardsSourceRef) for source in self.sources):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "profile sources must be StandardsSourceRef values"
            )
        ordered = tuple(sorted(self.sources, key=lambda source: source.sort_key))
        if len(set(source.sort_key for source in ordered)) != len(ordered):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "profile sources must not contain duplicates"
            )
        object.__setattr__(self, "sources", ordered)

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        version: str,
        sources: Sequence[StandardsSourceRef],
    ) -> "StandardsProfile":
        ordered = tuple(sorted(tuple(sources), key=lambda source: source.sort_key))
        digest = canonical_profile_digest(profile_id, version, ordered)
        return cls(profile_id=profile_id, version=version, digest=digest, sources=ordered)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StandardsProfile":
        if not isinstance(value, Mapping):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "standards profile must be an object"
            )
        candidate = dict(value)
        sources_value = candidate.get("sources", candidate.get("source_refs"))
        if "sources" in candidate and "source_refs" in candidate and candidate["sources"] != candidate["source_refs"]:
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "sources and source_refs disagree"
            )
        if not isinstance(sources_value, (list, tuple)):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "standards profile sources are required"
            )
        try:
            sources = tuple(StandardsSourceRef(**dict(source)) for source in sources_value)
            return cls(
                profile_id=candidate["profile_id"],
                version=candidate["version"],
                digest=candidate["digest"],
                sources=sources,
            )
        except KeyError as exc:
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", f"missing profile field: {exc.args[0]}"
            ) from exc
        except TypeError as exc:
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", f"invalid profile source: {exc}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "digest": self.digest,
            "sources": [source.to_dict() for source in self.sources],
        }

    def canonical_identity(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "sources": [source.to_dict() for source in self.sources],
        }



def canonical_profile_digest(
    profile_id: str,
    version: str,
    sources: Sequence[StandardsSourceRef],
) -> str:
    """Return the deterministic digest of profile identity and sorted sources."""

    ordered = tuple(sorted(tuple(sources), key=lambda source: source.sort_key))
    return _canonical_digest(
        {
            "profile_id": profile_id,
            "version": version,
            "sources": [source.to_dict() for source in ordered],
        }
    )


class ExactSourceReader(Protocol):
    """Port for reading one exact repository source without inference."""

    def read_exact(self, source: StandardsSourceRef) -> bytes: ...


class GitExactSourceReader:
    """Read exact committed text from a local Git object database."""

    def __init__(self, repository_root: str | Path) -> None:
        self.repository_root = Path(repository_root).resolve()

    def read_exact(self, source: StandardsSourceRef) -> bytes:
        object_ref = f"{source.commit_sha}:{source.path}"
        try:
            object_type = subprocess.run(
                ["git", "cat-file", "-t", object_ref],
                cwd=self.repository_root,
                check=False,
                capture_output=True,
            )
            if object_type.returncode != 0 or object_type.stdout.strip() != b"blob":
                raise StandardsResolutionError(
                    "STANDARDS_SOURCE_UNAVAILABLE",
                    f"exact source is not a committed blob: {source.path}",
                )
            result = subprocess.run(
                ["git", "show", object_ref],
                cwd=self.repository_root,
                check=False,
                capture_output=True,
            )
        except OSError as exc:
            raise StandardsResolutionError(
                "STANDARDS_SOURCE_UNAVAILABLE", f"git source reader unavailable: {exc}"
            ) from exc
        if result.returncode != 0:
            raise StandardsResolutionError(
                "STANDARDS_SOURCE_UNAVAILABLE",
                f"cannot read exact source {source.path} at {source.commit_sha}",
            )
        return result.stdout


@dataclass(frozen=True)
class MaterializedInstruction:
    source: StandardsSourceRef
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source.to_dict(), "content": self.content}


@dataclass(frozen=True)
class StandardsResolutionReceipt:
    profile_id: str
    version: str
    digest: str
    sources: tuple[StandardsSourceRef, ...]
    context_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "digest": self.digest,
            "source_count": len(self.sources),
            "source_refs": [source.to_dict() for source in self.sources],
            "context_digest": self.context_digest,
        }


@dataclass(frozen=True)
class StandardsSessionContext:
    receipt: StandardsResolutionReceipt
    instructions: tuple[MaterializedInstruction, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "standards": self.receipt.to_dict(),
            "instructions": [instruction.to_dict() for instruction in self.instructions],
        }


@dataclass(frozen=True)
class ResolvedStandards:
    profile: StandardsProfile
    instructions: tuple[MaterializedInstruction, ...]
    receipt: StandardsResolutionReceipt

    @property
    def session_context(self) -> StandardsSessionContext:
        return StandardsSessionContext(receipt=self.receipt, instructions=self.instructions)


class StandardsResolver:
    """Resolve and verify one exact standards profile into session context."""

    def __init__(self, source_reader: ExactSourceReader) -> None:
        self._source_reader = source_reader

    def resolve(self, profile: StandardsProfile | Mapping[str, Any]) -> ResolvedStandards:
        bound = (
            StandardsProfile.from_mapping(profile)
            if isinstance(profile, Mapping)
            else profile
        )
        if not isinstance(bound, StandardsProfile):
            raise StandardsResolutionError(
                "STANDARDS_PROFILE_INVALID", "profile must be StandardsProfile or object"
            )
        expected_profile_digest = canonical_profile_digest(
            bound.profile_id, bound.version, bound.sources
        )
        if bound.digest != expected_profile_digest:
            raise StandardsResolutionBlocked(
                "STANDARDS_PROFILE_DIGEST_MISMATCH",
                f"expected {expected_profile_digest}, got {bound.digest}",
            )

        instructions: list[MaterializedInstruction] = []
        for source in bound.sources:
            try:
                raw = self._source_reader.read_exact(source)
            except StandardsResolutionError:
                raise
            except Exception as exc:
                raise StandardsResolutionError(
                    "STANDARDS_SOURCE_UNAVAILABLE",
                    f"cannot read {source.path} at {source.commit_sha}: {exc}",
                ) from exc
            if not isinstance(raw, bytes):
                raise StandardsResolutionError(
                    "STANDARDS_SOURCE_INVALID", f"reader returned non-bytes for {source.path}"
                )
            actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            if actual_digest != source.blob_digest:
                raise StandardsResolutionBlocked(
                    "STANDARDS_SOURCE_DIGEST_MISMATCH",
                    f"source digest mismatch for {source.path}: expected {source.blob_digest}, got {actual_digest}",
                )
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise StandardsResolutionError(
                    "STANDARDS_SOURCE_INVALID", f"source is not UTF-8 text: {source.path}"
                ) from exc
            instructions.append(MaterializedInstruction(source=source, content=content))

        context_identity = {
            "profile": bound.canonical_identity(),
            "instructions": [
                {"source": item.source.to_dict(), "content_digest": item.source.blob_digest}
                for item in instructions
            ],
        }
        context_digest = _canonical_digest(context_identity)
        receipt = StandardsResolutionReceipt(
            profile_id=bound.profile_id,
            version=bound.version,
            digest=bound.digest,
            sources=bound.sources,
            context_digest=context_digest,
        )
        return ResolvedStandards(
            profile=bound,
            instructions=tuple(instructions),
            receipt=receipt,
        )


__all__ = [
    "ExactSourceReader",
    "GitExactSourceReader",
    "MaterializedInstruction",
    "ResolvedStandards",
    "StandardsProfile",
    "StandardsResolutionBlocked",
    "StandardsResolutionError",
    "StandardsResolutionReceipt",
    "StandardsResolver",
    "StandardsSessionContext",
    "StandardsSourceRef",
    "canonical_profile_digest",
]
