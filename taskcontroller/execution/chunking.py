"""TC-MBX-505 bounded chunked-review partitioning.

The partitioner is a pure source/evidence seam.  It binds every chunk to one
exact repository/commit/path/blob digest and records only stable ranges and
content digests.  It never reads a provider, persists a manifest, or activates
runtime fan-out.  A join is admissible only for the exact current source and
complete partition child set.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias

from taskcontroller.standards.resolver import StandardsSourceRef


CHUNKING_PROTOCOL = "dw.taskcontroller.chunked-review/v1"
DEFAULT_MAX_CHUNK_LINES = 200
DEFAULT_MAX_CHUNK_BYTES = 64 * 1024
MAX_CHUNKS = 64
MAX_CHUNK_LINES = 4096
MAX_CHUNK_BYTES = 4 * 1024 * 1024
MAX_CHUNK_ID_LENGTH = 128
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

SourceInput: TypeAlias = StandardsSourceRef | Mapping[str, Any]
ChunkInput: TypeAlias = "ChunkRef | Mapping[str, Any]"
PartitionInput: TypeAlias = "ChunkPartition | Mapping[str, Any]"


class ChunkPartitionError(ValueError):
    """Stable fail-closed error for partitioning and stale-join validation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        invalidated_child_ids: Sequence[str] = (),
    ) -> None:
        self.code = code
        self.invalidated_child_ids = tuple(invalidated_child_ids)
        super().__init__(f"{code}: {message}")


def _fail(
    code: str,
    message: str,
    *,
    invalidated_child_ids: Sequence[str] = (),
) -> None:
    raise ChunkPartitionError(
        code,
        message,
        invalidated_child_ids=invalidated_child_ids,
    )


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"chunk payload is not canonical JSON: {exc}")
    raise AssertionError("_fail must raise")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        _fail("SCHEMA_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return value


def _require_identifier(value: Any, field: str, *, max_bytes: int) -> str:
    if not isinstance(value, str):
        _fail("SCHEMA_INVALID", f"{field} must be a string")
    normalized = value.strip()
    if not normalized or not _ID_RE.fullmatch(normalized):
        _fail("SCHEMA_INVALID", f"{field} must be a stable identifier")
    if len(normalized.encode("utf-8")) > max_bytes:
        _fail("SCHEMA_INVALID", f"{field} exceeds {max_bytes} UTF-8 bytes")
    return normalized


def _positive_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("SCHEMA_INVALID", f"{field} must be a positive integer")
    if value > maximum:
        _fail("SCHEMA_INVALID", f"{field} exceeds {maximum}")
    return value


def _source(value: SourceInput) -> StandardsSourceRef:
    if isinstance(value, StandardsSourceRef):
        return value
    if isinstance(value, Mapping):
        try:
            return StandardsSourceRef(**dict(value))
        except Exception as exc:
            _fail("SOURCE_REF_INVALID", f"source reference is invalid: {exc}")
    _fail("SOURCE_REF_INVALID", "source reference must be an exact object")
    raise AssertionError("_fail must raise")


def _raw_bytes(value: Any) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    _fail("SOURCE_CONTENT_INVALID", "source content must be UTF-8 text or bytes")
    raise AssertionError("_fail must raise")


def _source_identity(source: StandardsSourceRef) -> tuple[str, str, str, str]:
    return (
        source.repository,
        source.commit_sha,
        source.path,
        source.blob_digest,
    )


@dataclass(frozen=True, slots=True)
class ChunkRange:
    """Inclusive line range plus half-open UTF-8 byte range."""

    line_start: int
    line_end: int
    byte_start: int
    byte_end: int

    def __post_init__(self) -> None:
        for field in ("line_start", "line_end", "byte_start", "byte_end"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _fail("RANGE_INVALID", f"{field} must be an integer >= 0")
        if self.line_start < 1 or self.line_end < self.line_start:
            _fail("RANGE_INVALID", "line range must be one-based and ordered")
        if self.byte_end <= self.byte_start:
            _fail("RANGE_INVALID", "byte range must be non-empty and ordered")

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        return (self.line_start, self.line_end, self.byte_start, self.byte_end)

    def to_dict(self) -> dict[str, int]:
        return {
            "line_start": self.line_start,
            "line_end": self.line_end,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChunkRange":
        if not isinstance(value, Mapping):
            _fail("RANGE_INVALID", "range must be an object")
        try:
            return cls(
                line_start=value["line_start"],
                line_end=value["line_end"],
                byte_start=value["byte_start"],
                byte_end=value["byte_end"],
            )
        except KeyError as exc:
            _fail("RANGE_INVALID", f"missing range field: {exc.args[0]}")
        raise AssertionError("_fail must raise")


@dataclass(frozen=True, slots=True)
class ChunkRef:
    """Reference-only child input for one exact source range."""

    chunk_id: str
    source_ref: StandardsSourceRef
    source_digest: str
    range: ChunkRange
    content_digest: str

    def __post_init__(self) -> None:
        _require_identifier(self.chunk_id, "chunk_id", max_bytes=MAX_CHUNK_ID_LENGTH)
        if not isinstance(self.source_ref, StandardsSourceRef):
            _fail("SOURCE_REF_INVALID", "chunk source_ref must be StandardsSourceRef")
        _require_digest(self.source_digest, "source_digest")
        if self.source_digest != self.source_ref.blob_digest:
            _fail("SOURCE_VERSION_MISMATCH", "chunk source digest differs from source_ref")
        if not isinstance(self.range, ChunkRange):
            _fail("RANGE_INVALID", "chunk range must be ChunkRange")
        _require_digest(self.content_digest, "content_digest")

    @property
    def child_id(self) -> str:
        """Child-contract-compatible stable identity alias."""

        return self.chunk_id

    @property
    def source_identity(self) -> tuple[str, str, str, str]:
        return _source_identity(self.source_ref)

    @property
    def sort_key(self) -> tuple[int, int, str]:
        return (self.range.byte_start, self.range.byte_end, self.chunk_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_ref": self.source_ref.to_dict(),
            "source_digest": self.source_digest,
            "range": self.range.to_dict(),
            "content_digest": self.content_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChunkRef":
        if not isinstance(value, Mapping):
            _fail("CHUNK_SET_INVALID", "chunk must be an object")
        try:
            return cls(
                chunk_id=value["chunk_id"],
                source_ref=_source(value["source_ref"]),
                source_digest=value["source_digest"],
                range=ChunkRange.from_dict(value["range"]),
                content_digest=value["content_digest"],
            )
        except KeyError as exc:
            _fail("CHUNK_SET_INVALID", f"missing chunk field: {exc.args[0]}")
        raise AssertionError("_fail must raise")


@dataclass(frozen=True, slots=True)
class ChunkPartition:
    """Immutable deterministic partition manifest without raw artifact bytes."""

    source_ref: StandardsSourceRef
    source_digest: str
    max_lines: int | None
    max_bytes: int | None
    chunks: tuple[ChunkRef, ...]
    partition_digest: str
    protocol: str = CHUNKING_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != CHUNKING_PROTOCOL:
            _fail("UNSUPPORTED_PROTOCOL", f"expected {CHUNKING_PROTOCOL}")
        if not isinstance(self.source_ref, StandardsSourceRef):
            _fail("SOURCE_REF_INVALID", "partition source_ref must be StandardsSourceRef")
        _require_digest(self.source_digest, "source_digest")
        if self.source_digest != self.source_ref.blob_digest:
            _fail("SOURCE_VERSION_MISMATCH", "partition source digest differs from source_ref")
        if self.max_lines is not None:
            _positive_int(self.max_lines, "max_lines", maximum=MAX_CHUNK_LINES)
        if self.max_bytes is not None:
            _positive_int(self.max_bytes, "max_bytes", maximum=MAX_CHUNK_BYTES)
        if self.max_lines is None and self.max_bytes is None:
            _fail("PARTITION_POLICY_INVALID", "at least one chunk bound is required")
        normalized = tuple(self.chunks)
        if not normalized:
            _fail("CHUNK_SET_INVALID", "partition must contain at least one chunk")
        if any(not isinstance(chunk, ChunkRef) for chunk in normalized):
            _fail("CHUNK_SET_INVALID", "partition chunks must be ChunkRef values")
        ordered = tuple(sorted(normalized, key=lambda chunk: chunk.sort_key))
        if ordered != normalized:
            object.__setattr__(self, "chunks", ordered)
        ids = tuple(chunk.chunk_id for chunk in ordered)
        if len(set(ids)) != len(ids):
            _fail("CHUNK_SET_INVALID", "partition chunk IDs must be unique")
        expected_identity = _source_identity(self.source_ref)
        if any(chunk.source_identity != expected_identity for chunk in ordered):
            _fail("SOURCE_VERSION_MISMATCH", "partition contains a different source version")
        _require_digest(self.partition_digest, "partition_digest")
        expected_digest = _digest(self._payload(chunks=ordered))
        if self.partition_digest != expected_digest:
            _fail("DIGEST_MISMATCH", "partition digest does not match canonical bytes")

    def _payload(self, *, chunks: Sequence[ChunkRef] | None = None) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "source_ref": self.source_ref.to_dict(),
            "source_digest": self.source_digest,
            "max_lines": self.max_lines,
            "max_bytes": self.max_bytes,
            "chunks": [chunk.to_dict() for chunk in (chunks or self.chunks)],
        }

    @property
    def child_ids(self) -> tuple[str, ...]:
        return tuple(chunk.chunk_id for chunk in self.chunks)

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "partition_digest": self.partition_digest}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChunkPartition":
        if not isinstance(value, Mapping):
            _fail("SCHEMA_INVALID", "partition must be an object")
        try:
            chunks_value = value["chunks"]
            if not isinstance(chunks_value, (list, tuple)) or any(
                not isinstance(item, Mapping) for item in chunks_value
            ):
                _fail("CHUNK_SET_INVALID", "chunks must be an array of objects")
            chunks = tuple(ChunkRef.from_dict(item) for item in chunks_value)
            return cls(
                source_ref=_source(value["source_ref"]),
                source_digest=value["source_digest"],
                max_lines=value.get("max_lines"),
                max_bytes=value.get("max_bytes"),
                chunks=chunks,
                partition_digest=value["partition_digest"],
                protocol=value.get("protocol", CHUNKING_PROTOCOL),
            )
        except KeyError as exc:
            _fail("SCHEMA_INVALID", f"missing partition field: {exc.args[0]}")
        except TypeError as exc:
            _fail("CHUNK_SET_INVALID", f"chunks must be iterable: {exc}")
        raise AssertionError("_fail must raise")


# The architecture calls the durable future artifact a Fanout Manifest.  The
# base partitioner remains an in-memory/reference-only manifest until the later
# hardening task owns persistence.
ChunkManifest = ChunkPartition


class ChunkJoinStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ChunkJoinDecision:
    """Explicit join result; BLOCKED always carries invalidated child IDs."""

    status: ChunkJoinStatus
    reason_code: str
    manifest_digest: str
    normalized_chunks: tuple[ChunkRef, ...] = ()
    invalidated_child_ids: tuple[str, ...] = ()

    @property
    def joinable(self) -> bool:
        return self.status is ChunkJoinStatus.READY

    @property
    def normalized_digest(self) -> str:
        return _digest(
            {
                "protocol": CHUNKING_PROTOCOL,
                "manifest_digest": self.manifest_digest,
                "chunks": [chunk.to_dict() for chunk in self.normalized_chunks],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": CHUNKING_PROTOCOL,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "manifest_digest": self.manifest_digest,
            "normalized_chunks": [chunk.to_dict() for chunk in self.normalized_chunks],
            "normalized_digest": self.normalized_digest,
            "invalidated_child_ids": list(self.invalidated_child_ids),
        }


def _join_blocked(
    partition: ChunkPartition,
    reason_code: str,
    *,
    normalized_chunks: Sequence[ChunkRef] = (),
) -> ChunkJoinDecision:
    return ChunkJoinDecision(
        status=ChunkJoinStatus.BLOCKED,
        reason_code=reason_code,
        manifest_digest=partition.partition_digest,
        normalized_chunks=tuple(sorted(normalized_chunks, key=lambda chunk: chunk.sort_key)),
        invalidated_child_ids=partition.child_ids,
    )


class ChunkPartitioner:
    """Create and validate deterministic source-bound chunk partitions."""

    def __init__(
        self,
        *,
        max_lines: int | None = DEFAULT_MAX_CHUNK_LINES,
        max_bytes: int | None = DEFAULT_MAX_CHUNK_BYTES,
        max_chunks: int = MAX_CHUNKS,
    ) -> None:
        if max_lines is None and max_bytes is None:
            _fail("PARTITION_POLICY_INVALID", "at least one chunk bound is required")
        if max_lines is not None:
            _positive_int(max_lines, "max_lines", maximum=MAX_CHUNK_LINES)
        if max_bytes is not None:
            _positive_int(max_bytes, "max_bytes", maximum=MAX_CHUNK_BYTES)
        _positive_int(max_chunks, "max_chunks", maximum=MAX_CHUNKS)
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.max_chunks = max_chunks

    def partition(self, source: SourceInput, content: str | bytes | bytearray) -> ChunkPartition:
        bound_source = _source(source)
        raw = _raw_bytes(content)
        actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual_digest != bound_source.blob_digest:
            _fail(
                "SOURCE_DIGEST_MISMATCH",
                f"expected {bound_source.blob_digest}, got {actual_digest}",
            )
        if not raw:
            _fail("SOURCE_CONTENT_INVALID", "empty source cannot produce review chunks")

        units = raw.splitlines(keepends=True)
        chunks: list[ChunkRef] = []
        pending: list[bytes] = []
        pending_start_line = 1
        pending_start_byte = 0
        current_byte = 0

        def emit(end_line: int, end_byte: int) -> None:
            if not pending:
                return
            chunk_bytes = b"".join(pending)
            content_digest = "sha256:" + hashlib.sha256(chunk_bytes).hexdigest()
            chunk_range = ChunkRange(
                line_start=pending_start_line,
                line_end=end_line,
                byte_start=pending_start_byte,
                byte_end=end_byte,
            )
            chunk_id = "chunk-" + hashlib.sha256(
                _canonical_bytes(
                    {
                        "protocol": CHUNKING_PROTOCOL,
                        "source_ref": bound_source.to_dict(),
                        "range": chunk_range.to_dict(),
                        "content_digest": content_digest,
                    }
                )
            ).hexdigest()[:32]
            chunks.append(
                ChunkRef(
                    chunk_id=chunk_id,
                    source_ref=bound_source,
                    source_digest=bound_source.blob_digest,
                    range=chunk_range,
                    content_digest=content_digest,
                )
            )
            if len(chunks) > self.max_chunks:
                _fail(
                    "CHUNK_COUNT_EXCEEDED",
                    f"partition exceeds max_chunks={self.max_chunks}",
                )

        for index, unit in enumerate(units, start=1):
            if self.max_bytes is not None and len(unit) > self.max_bytes:
                _fail(
                    "CHUNK_LIMIT_EXCEEDED",
                    f"line {index} exceeds max_bytes={self.max_bytes}",
                )
            would_exceed_lines = (
                self.max_lines is not None and len(pending) >= self.max_lines
            )
            would_exceed_bytes = (
                self.max_bytes is not None
                and bool(pending)
                and len(b"".join(pending)) + len(unit) > self.max_bytes
            )
            if pending and (would_exceed_lines or would_exceed_bytes):
                emit(index - 1, current_byte)
                pending = []
                pending_start_line = index
                pending_start_byte = current_byte
            pending.append(unit)
            current_byte += len(unit)

        emit(len(units), current_byte)
        payload = {
            "protocol": CHUNKING_PROTOCOL,
            "source_ref": bound_source.to_dict(),
            "source_digest": bound_source.blob_digest,
            "max_lines": self.max_lines,
            "max_bytes": self.max_bytes,
            "chunks": [chunk.to_dict() for chunk in chunks],
        }
        return ChunkPartition(
            source_ref=bound_source,
            source_digest=bound_source.blob_digest,
            max_lines=self.max_lines,
            max_bytes=self.max_bytes,
            chunks=tuple(chunks),
            partition_digest=_digest(payload),
        )

    @staticmethod
    def from_dict(value: Mapping[str, Any]) -> ChunkPartition:
        return ChunkPartition.from_dict(value)

    def join(
        self,
        partition: PartitionInput,
        chunks: Sequence[ChunkInput],
        *,
        current_source: SourceInput | None = None,
        current_content: str | bytes | bytearray | None = None,
    ) -> ChunkJoinDecision:
        try:
            bound_partition = (
                partition
                if isinstance(partition, ChunkPartition)
                else ChunkPartition.from_dict(partition)
            )
        except ChunkPartitionError:
            raise

        if current_source is not None:
            candidate_source = _source(current_source)
            if _source_identity(candidate_source) != _source_identity(bound_partition.source_ref):
                return _join_blocked(bound_partition, "SOURCE_VERSION_MISMATCH")
            if current_content is not None:
                raw = _raw_bytes(current_content)
                actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
                if actual_digest != bound_partition.source_digest:
                    return _join_blocked(bound_partition, "SOURCE_VERSION_MISMATCH")

        if isinstance(chunks, (str, bytes, Mapping)):
            return _join_blocked(bound_partition, "CHUNK_SET_INVALID")
        try:
            received = tuple(
                item if isinstance(item, ChunkRef) else ChunkRef.from_dict(item)
                for item in chunks
            )
        except (ChunkPartitionError, TypeError):
            return _join_blocked(bound_partition, "CHUNK_SET_INVALID")

        if len({chunk.chunk_id for chunk in received}) != len(received):
            return _join_blocked(bound_partition, "CHUNK_SET_INVALID", normalized_chunks=received)
        expected_identity = _source_identity(bound_partition.source_ref)
        if any(chunk.source_identity != expected_identity for chunk in received):
            return _join_blocked(
                bound_partition,
                "SOURCE_VERSION_MISMATCH",
                normalized_chunks=received,
            )

        expected = {chunk.chunk_id: chunk for chunk in bound_partition.chunks}
        received_ids = {chunk.chunk_id for chunk in received}
        if received_ids != set(expected):
            reason = (
                "CHUNK_SET_INCOMPLETE"
                if received_ids < set(expected)
                else "CHUNK_SET_INVALID"
            )
            return _join_blocked(bound_partition, reason, normalized_chunks=received)
        if any(expected[chunk.chunk_id] != chunk for chunk in received):
            return _join_blocked(
                bound_partition,
                "CHUNK_DIGEST_MISMATCH",
                normalized_chunks=received,
            )

        normalized = tuple(sorted(received, key=lambda chunk: chunk.sort_key))
        return ChunkJoinDecision(
            status=ChunkJoinStatus.READY,
            reason_code="JOIN_READY",
            manifest_digest=bound_partition.partition_digest,
            normalized_chunks=normalized,
        )

    def require_joinable(
        self,
        partition: PartitionInput,
        chunks: Sequence[ChunkInput],
        *,
        current_source: SourceInput | None = None,
        current_content: str | bytes | bytearray | None = None,
    ) -> ChunkJoinDecision:
        decision = self.join(
            partition,
            chunks,
            current_source=current_source,
            current_content=current_content,
        )
        if not decision.joinable:
            raise ChunkPartitionError(
                decision.reason_code,
                "chunked review join is blocked",
                invalidated_child_ids=decision.invalidated_child_ids,
            )
        return decision


ChunkedReviewPartitioner = ChunkPartitioner
ChunkPartitionManifest = ChunkPartition


def partition_chunks(
    source: SourceInput,
    content: str | bytes | bytearray,
    *,
    max_lines: int | None = DEFAULT_MAX_CHUNK_LINES,
    max_bytes: int | None = DEFAULT_MAX_CHUNK_BYTES,
    max_chunks: int = MAX_CHUNKS,
) -> ChunkPartition:
    """Functional entrypoint for one deterministic partition."""

    return ChunkPartitioner(
        max_lines=max_lines,
        max_bytes=max_bytes,
        max_chunks=max_chunks,
    ).partition(source, content)
