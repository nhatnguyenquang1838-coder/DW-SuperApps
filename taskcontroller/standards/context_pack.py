"""Bounded, exact-source TaskController session context packs.

The pack is a pure materialization boundary for one mailbox request.  It accepts
only explicit task source/evidence references and an already-resolved standards
context.  It does not accept or replay Slack, GPT, DM or conversation history,
and it has no transport/provider side effects.
"""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.standards.resolver import (
    MaterializedInstruction,
    ResolvedStandards,
    StandardsResolutionError,
    StandardsSessionContext,
    StandardsSourceRef,
)


CONTEXT_PACK_PROTOCOL = "dw.taskcontroller.context-pack/v1"
_CONTEXT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_MAX_SOURCE_REFS = 16
DEFAULT_MAX_EVIDENCE_REFS = 16
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024
DEFAULT_MAX_SINGLE_BYTES = 128 * 1024


class ContextPackError(TaskControllerValidationError):
    """Stable fail-closed error for context-pack validation/materialization."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class EvidenceRef:
    """One immutable, digest-bound evidence artifact reference."""

    ref: str
    digest: str
    media_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise ContextPackError("CONTEXT_EVIDENCE_REF_INVALID", "ref must be non-empty")
        if not isinstance(self.digest, str) or not _CONTEXT_DIGEST_RE.fullmatch(self.digest):
            raise ContextPackError(
                "CONTEXT_EVIDENCE_REF_INVALID",
                "digest must be sha256:<64 lowercase hex>",
            )
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ContextPackError(
                "CONTEXT_EVIDENCE_REF_INVALID", "media_type must be non-empty"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceRef":
        if not isinstance(value, Mapping):
            raise ContextPackError(
                "CONTEXT_EVIDENCE_REF_INVALID", "evidence reference must be an object"
            )
        candidate = dict(value)
        ref = candidate.get("ref", candidate.get("evidence_ref", candidate.get("artifact_ref")))
        digest = candidate.get("digest", candidate.get("content_digest"))
        try:
            return cls(
                ref=ref,
                digest=digest,
                media_type=candidate.get("media_type", "application/octet-stream"),
            )
        except TypeError as exc:
            raise ContextPackError(
                "CONTEXT_EVIDENCE_REF_INVALID", f"malformed evidence reference: {exc}"
            ) from exc

    @classmethod
    def from_value(cls, value: Any) -> "EvidenceRef":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        raise ContextPackError(
            "CONTEXT_EVIDENCE_REF_INVALID",
            "evidence references require an exact ref and content digest",
        )

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.ref, self.digest, self.media_type)

    def to_dict(self) -> dict[str, str]:
        return {
            "ref": self.ref,
            "digest": self.digest,
            "media_type": self.media_type,
        }


class ExactTaskSourceReader(Protocol):
    """Port for reading one exact committed task source."""

    def read_exact(self, source: StandardsSourceRef) -> bytes: ...


class ExactEvidenceReader(Protocol):
    """Port for reading one exact immutable evidence artifact."""

    def read_exact(self, evidence: EvidenceRef) -> bytes: ...


@dataclass(frozen=True)
class ContextPackLimits:
    """Bounded materialization limits for one task context pack."""

    max_sources: int = DEFAULT_MAX_SOURCE_REFS
    max_evidence: int = DEFAULT_MAX_EVIDENCE_REFS
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_single_bytes: int = DEFAULT_MAX_SINGLE_BYTES

    def __post_init__(self) -> None:
        for name in (
            "max_sources",
            "max_evidence",
            "max_total_bytes",
            "max_single_bytes",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContextPackError(
                    "CONTEXT_LIMIT_INVALID", f"{name} must be an integer >= 0"
                )
        if self.max_single_bytes > self.max_total_bytes:
            raise ContextPackError(
                "CONTEXT_LIMIT_INVALID",
                "max_single_bytes cannot exceed max_total_bytes",
            )


@dataclass(frozen=True)
class MaterializedContextSource:
    """Exact task source content selected by the request."""

    source: StandardsSourceRef
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source.to_dict(), "content": self.content}


@dataclass(frozen=True)
class MaterializedEvidence:
    """Exact evidence bytes selected by the request."""

    reference: EvidenceRef
    content: bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference.to_dict(),
            "content_base64": base64.b64encode(self.content).decode("ascii"),
        }


@dataclass(frozen=True)
class TaskContextPack:
    """Immutable bounded task context plus a reproducible reference inventory."""

    standards: StandardsSessionContext
    sources: tuple[MaterializedContextSource, ...]
    evidence: tuple[MaterializedEvidence, ...]
    _inventory: Mapping[str, Any]
    inventory_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "_inventory", copy.deepcopy(dict(self._inventory)))

    @property
    def inventory(self) -> dict[str, Any]:
        """Return a defensive copy of the canonical reference inventory."""

        return copy.deepcopy(dict(self._inventory))

    @property
    def source_pack_digest(self) -> str:
        """Compatibility name for the digest consumed by bootstrap receipts."""

        return self.inventory_digest

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self._inventory)

    def digest(self) -> str:
        return self.inventory_digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": CONTEXT_PACK_PROTOCOL,
            "inventory": self.inventory,
            "inventory_digest": self.inventory_digest,
            "standards": self.standards.to_dict(),
            "sources": [item.to_dict() for item in self.sources],
            "evidence": [item.to_dict() for item in self.evidence],
        }


class ContextPackBuilder:
    """Build one bounded pack from exact injected source/evidence readers."""

    def __init__(
        self,
        source_reader: ExactTaskSourceReader,
        evidence_reader: ExactEvidenceReader | None = None,
        *,
        limits: ContextPackLimits | None = None,
    ) -> None:
        if not hasattr(source_reader, "read_exact"):
            raise ContextPackError(
                "CONTEXT_READER_INVALID", "source reader must provide read_exact"
            )
        if evidence_reader is not None and not hasattr(evidence_reader, "read_exact"):
            raise ContextPackError(
                "CONTEXT_READER_INVALID", "evidence reader must provide read_exact"
            )
        self._source_reader = source_reader
        self._evidence_reader = evidence_reader or source_reader
        self._limits = limits or ContextPackLimits()

    def build(
        self,
        *,
        source_refs: Sequence[StandardsSourceRef | Mapping[str, Any]],
        evidence_refs: Sequence[EvidenceRef | Mapping[str, Any]],
        standards: StandardsSessionContext | ResolvedStandards | None,
    ) -> TaskContextPack:
        session_context = _standards_context(standards)
        sources = _normalize_sources(source_refs)
        evidence = _normalize_evidence(evidence_refs)
        if len(sources) > self._limits.max_sources:
            raise ContextPackError(
                "CONTEXT_SOURCE_LIMIT_EXCEEDED",
                f"maximum source refs is {self._limits.max_sources}",
            )
        if len(evidence) > self._limits.max_evidence:
            raise ContextPackError(
                "CONTEXT_EVIDENCE_LIMIT_EXCEEDED",
                f"maximum evidence refs is {self._limits.max_evidence}",
            )

        standards_sources = {
            item.source.sort_key: item for item in session_context.instructions
        }
        materialized_sources: list[MaterializedContextSource] = []
        total_bytes = sum(
            len(item.content.encode("utf-8")) for item in session_context.instructions
        )
        _check_size(total_bytes, self._limits, "standards")

        for source in sources:
            standard_instruction = standards_sources.get(source.sort_key)
            if standard_instruction is not None:
                raw = standard_instruction.content.encode("utf-8")
            else:
                raw = _read_source(self._source_reader, source)
            _check_content_digest(raw, source.blob_digest, "CONTEXT_SOURCE_DIGEST_MISMATCH", source.path)
            _check_size(len(raw), self._limits, source.path)
            total_bytes += len(raw)
            _check_size(total_bytes, self._limits, "total context")
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ContextPackError(
                    "CONTEXT_SOURCE_INVALID", f"source is not UTF-8 text: {source.path}"
                ) from exc
            materialized_sources.append(
                MaterializedContextSource(source=source, content=content)
            )

        materialized_evidence: list[MaterializedEvidence] = []
        for reference in evidence:
            raw = _read_evidence(self._evidence_reader, reference)
            _check_content_digest(
                raw,
                reference.digest,
                "CONTEXT_EVIDENCE_DIGEST_MISMATCH",
                reference.ref,
            )
            _check_size(len(raw), self._limits, reference.ref)
            total_bytes += len(raw)
            _check_size(total_bytes, self._limits, "total context")
            materialized_evidence.append(
                MaterializedEvidence(reference=reference, content=bytes(raw))
            )

        inventory = {
            "protocol": CONTEXT_PACK_PROTOCOL,
            "standards": session_context.receipt.to_dict(),
            "source_refs": [item.to_dict() for item in sources],
            "evidence_refs": [item.to_dict() for item in evidence],
        }
        inventory_digest = _digest(inventory)
        return TaskContextPack(
            standards=session_context,
            sources=tuple(materialized_sources),
            evidence=tuple(materialized_evidence),
            _inventory=inventory,
            inventory_digest=inventory_digest,
        )


BoundedTaskContextPackBuilder = ContextPackBuilder
ContextPack = TaskContextPack


def build_context_pack(
    source_reader: ExactTaskSourceReader,
    evidence_reader: ExactEvidenceReader | None = None,
    *,
    source_refs: Sequence[StandardsSourceRef | Mapping[str, Any]],
    evidence_refs: Sequence[EvidenceRef | Mapping[str, Any]],
    standards: StandardsSessionContext | ResolvedStandards | None,
    limits: ContextPackLimits | None = None,
) -> TaskContextPack:
    """Functional alias for the bounded builder."""

    return ContextPackBuilder(
        source_reader,
        evidence_reader,
        limits=limits,
    ).build(source_refs=source_refs, evidence_refs=evidence_refs, standards=standards)


def _standards_context(
    value: StandardsSessionContext | ResolvedStandards | None,
) -> StandardsSessionContext:
    if value is None:
        raise ContextPackError(
            "CONTEXT_STANDARDS_REQUIRED",
            "resolved standards session context is required",
        )
    if isinstance(value, ResolvedStandards):
        value = value.session_context
    if not isinstance(value, StandardsSessionContext):
        raise ContextPackError(
            "CONTEXT_STANDARDS_INVALID",
            "standards must be StandardsSessionContext or ResolvedStandards",
        )
    if not value.instructions or not value.receipt.sources:
        raise ContextPackError(
            "CONTEXT_STANDARDS_INVALID",
            "standards context must contain resolved instructions and sources",
        )
    instruction_sources = tuple(item.source for item in value.instructions)
    if instruction_sources != value.receipt.sources:
        raise ContextPackError(
            "CONTEXT_STANDARDS_INVALID",
            "standards receipt sources do not match materialized instructions",
        )
    return value


def _normalize_sources(
    values: Sequence[StandardsSourceRef | Mapping[str, Any]],
) -> tuple[StandardsSourceRef, ...]:
    if not isinstance(values, (list, tuple)):
        raise ContextPackError("CONTEXT_SOURCE_REF_INVALID", "source_refs must be an array")
    normalized: list[StandardsSourceRef] = []
    for value in values:
        if isinstance(value, StandardsSourceRef):
            normalized.append(value)
            continue
        if not isinstance(value, Mapping):
            raise ContextPackError(
                "CONTEXT_SOURCE_REF_INVALID", "source reference must be an object"
            )
        try:
            normalized.append(StandardsSourceRef(**dict(value)))
        except (KeyError, TypeError, StandardsResolutionError) as exc:
            raise ContextPackError(
                "CONTEXT_SOURCE_REF_INVALID", f"malformed source reference: {exc}"
            ) from exc
    ordered = tuple(sorted(normalized, key=lambda item: item.sort_key))
    if len({item.sort_key for item in ordered}) != len(ordered):
        raise ContextPackError(
            "CONTEXT_DUPLICATE_REF", "source_refs must not contain duplicates"
        )
    return ordered


def _normalize_evidence(
    values: Sequence[EvidenceRef | Mapping[str, Any]],
) -> tuple[EvidenceRef, ...]:
    if not isinstance(values, (list, tuple)):
        raise ContextPackError("CONTEXT_EVIDENCE_REF_INVALID", "evidence_refs must be an array")
    try:
        normalized = tuple(EvidenceRef.from_value(value) for value in values)
    except ContextPackError:
        raise
    ordered = tuple(sorted(normalized, key=lambda item: item.sort_key))
    if len({item.sort_key for item in ordered}) != len(ordered):
        raise ContextPackError(
            "CONTEXT_DUPLICATE_REF", "evidence_refs must not contain duplicates"
        )
    return ordered


def _read_source(reader: ExactTaskSourceReader, source: StandardsSourceRef) -> bytes:
    try:
        raw = reader.read_exact(source)
    except Exception as exc:
        raise ContextPackError(
            "CONTEXT_SOURCE_UNAVAILABLE",
            f"cannot read exact source {source.path} at {source.commit_sha}",
        ) from exc
    if not isinstance(raw, bytes):
        raise ContextPackError(
            "CONTEXT_SOURCE_INVALID", f"source reader returned non-bytes: {source.path}"
        )
    return raw


def _read_evidence(reader: ExactEvidenceReader, reference: EvidenceRef) -> bytes:
    try:
        raw = reader.read_exact(reference)
    except Exception as exc:
        raise ContextPackError(
            "CONTEXT_EVIDENCE_UNAVAILABLE",
            f"cannot read exact evidence {reference.ref}",
        ) from exc
    if not isinstance(raw, bytes):
        raise ContextPackError(
            "CONTEXT_EVIDENCE_INVALID",
            f"evidence reader returned non-bytes: {reference.ref}",
        )
    return raw


def _check_content_digest(raw: bytes, expected: str, code: str, ref: str) -> None:
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ContextPackError(
            code, f"content digest mismatch for {ref}: expected {expected}, got {actual}"
        )


def _check_size(size: int, limits: ContextPackLimits, ref: str) -> None:
    if size > limits.max_single_bytes:
        raise ContextPackError(
            "CONTEXT_SIZE_LIMIT_EXCEEDED",
            f"materialized item exceeds {limits.max_single_bytes} bytes: {ref}",
        )
    if size > limits.max_total_bytes:
        raise ContextPackError(
            "CONTEXT_SIZE_LIMIT_EXCEEDED",
            f"materialized context exceeds {limits.max_total_bytes} bytes: {ref}",
        )


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContextPackError(
            "CONTEXT_INVENTORY_INVALID", f"inventory is not canonical JSON: {exc}"
        ) from exc


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


__all__ = [
    "BoundedTaskContextPackBuilder",
    "CONTEXT_PACK_PROTOCOL",
    "ContextPack",
    "ContextPackBuilder",
    "ContextPackError",
    "ContextPackLimits",
    "ExactEvidenceReader",
    "ExactTaskSourceReader",
    "EvidenceRef",
    "MaterializedContextSource",
    "MaterializedEvidence",
    "TaskContextPack",
    "build_context_pack",
]
