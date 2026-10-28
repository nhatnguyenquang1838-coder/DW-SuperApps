"""Exact read-only projection-prefix boundary for qualification runs.

A source adapter may read a pinned durable prefix, but this protocol intentionally
has no append/update/delete methods. Graph checkpoints keep only the boundary and
digest; event history is re-read from the canonical source when a graph resumes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Protocol

from .events import RunProjectionEvent
from .qualification_models import (
    CheckStatus,
    DwoRunId,
    QualificationCheck,
    QualificationSubject,
)

PREFIX_SCHEMA_VERSION = "dwo.qualification-prefix/1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class ProjectionPrefix:
    dwo_run_id: DwoRunId
    source_repository: str
    source_sha: str
    lifecycle_profile: str
    projection_contract_version: str
    reducer_version: str
    durable_position: str
    events: tuple[RunProjectionEvent, ...]
    semantic_checks: tuple[QualificationCheck, ...] = ()
    schema_version: str = PREFIX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PREFIX_SCHEMA_VERSION:
            raise ValueError(f"unsupported ProjectionPrefix schema: {self.schema_version!r}")
        if not isinstance(self.dwo_run_id, DwoRunId):
            raise TypeError("dwo_run_id must be a DwoRunId")
        for name in (
            "source_repository", "source_sha", "lifecycle_profile",
            "projection_contract_version", "reducer_version", "durable_position",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        events = tuple(self.events)
        if any(not isinstance(event, RunProjectionEvent) for event in events):
            raise TypeError("events must contain RunProjectionEvent objects")
        for event in events:
            if event.run_id != self.dwo_run_id.value:
                raise ValueError("projection prefix contains an event from a different DWO run")
            if event.read_only_projection is not True:
                raise ValueError("qualification source accepts only read_only_projection events")
        checks = tuple(sorted(self.semantic_checks, key=lambda check: check.check_id))
        if len({check.check_id for check in checks}) != len(checks):
            raise ValueError("semantic check ids must be unique")
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "semantic_checks", checks)

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def history_digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "dwo_run_id": self.dwo_run_id.value,
            "source_repository": self.source_repository,
            "source_sha": self.source_sha,
            "lifecycle_profile": self.lifecycle_profile,
            "projection_contract_version": self.projection_contract_version,
            "reducer_version": self.reducer_version,
            "durable_position": self.durable_position,
            "events": [event.to_dict() for event in self.events],
        }
        return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    @property
    def semantic_facts_digest(self) -> str:
        payload = [check.to_dict() for check in self.semantic_checks]
        return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PrefixBindingResult:
    status: CheckStatus
    current: bool
    evidence_refs: tuple[str, ...]
    reasons: tuple[str, ...]


def validate_prefix_binding(prefix: ProjectionPrefix, subject: QualificationSubject) -> PrefixBindingResult:
    """Compare the read prefix against every immutable subject binding."""
    mismatches: list[str] = []
    pairs = (
        ("dwo_run_id", prefix.dwo_run_id.value, subject.dwo_run_id.value),
        ("source_repository", prefix.source_repository, subject.source_repository),
        ("source_sha", prefix.source_sha, subject.source_sha),
        ("lifecycle_profile", prefix.lifecycle_profile, subject.lifecycle_profile),
        ("projection_contract_version", prefix.projection_contract_version, subject.projection_contract_version),
        ("reducer_version", prefix.reducer_version, subject.reducer_version),
        ("durable_position", prefix.durable_position, subject.durable_position),
    )
    for field, observed, expected in pairs:
        if observed != expected:
            mismatches.append(f"{field}: observed {observed!r} != subject {expected!r}")
    if mismatches:
        return PrefixBindingResult(
            status=CheckStatus.DRIFTED,
            current=False,
            evidence_refs=(f"evidence://qualification/prefix/{prefix.history_digest.removeprefix('sha256:')}",),
            reasons=tuple(mismatches),
        )
    if prefix.event_count == 0:
        return PrefixBindingResult(
            status=CheckStatus.UNKNOWN,
            current=True,
            evidence_refs=(f"evidence://qualification/prefix/{prefix.history_digest.removeprefix('sha256:')}",),
            reasons=("durable prefix is empty; semantic state cannot be established",),
        )
    return PrefixBindingResult(
        status=CheckStatus.PASS,
        current=True,
        evidence_refs=(f"evidence://qualification/prefix/{prefix.history_digest.removeprefix('sha256:')}",),
        reasons=(),
    )


class ProjectionSourceUnavailable(RuntimeError):
    """The exact durable prefix cannot be read without falling back."""


class ReadOnlyProjectionSource(Protocol):
    """Host-provided exact-prefix reader. Deliberately exposes no mutation API."""

    def read_prefix(self, subject: QualificationSubject) -> ProjectionPrefix:
        """Read the prefix at subject.durable_position or raise on unavailable data."""
        ...
