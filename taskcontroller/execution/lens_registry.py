"""Capability-based review-lens registry for bounded cross-review planning.

The registry is a pure immutable snapshot.  It describes review lenses and
capabilities but does not invoke reviewers, providers, networking, or runtime
fan-out.  A task-specific lens is therefore an extension of the registry
contract, not a kernel edit.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from taskcontroller.execution.errors import ExecutionFabricError


LENS_REGISTRY_PROTOCOL = "dw.taskcontroller.lens-registry/v1"
MAX_LENS_ID_LENGTH = 128
MAX_CAPABILITY_LENGTH = 64
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class LensNotFoundError(ExecutionFabricError):
    """Raised when a requested lens is not in the immutable registry snapshot."""


def _validate_token(value: Any, name: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionFabricError(f"{name} must be a non-empty string")
    if len(value.encode("utf-8")) > max_length:
        raise ExecutionFabricError(f"{name} exceeds {max_length} UTF-8 bytes")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ExecutionFabricError(f"{name} must be a stable identifier")
    return value


def _normalize_capabilities(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ExecutionFabricError(f"{field_name} must be a sequence of capability identifiers")
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise ExecutionFabricError(
            f"{field_name} must be a sequence of capability identifiers"
        ) from exc
    if not raw:
        raise ExecutionFabricError(f"{field_name} must contain at least one capability")
    normalized = tuple(
        sorted(
            _validate_token(value, f"{field_name} item", max_length=MAX_CAPABILITY_LENGTH)
            for value in raw
        )
    )
    if len(set(normalized)) != len(normalized):
        raise ExecutionFabricError(f"{field_name} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class ReviewLens:
    """A declarative review lens identified by stable capabilities."""

    lens_id: str
    capabilities: tuple[str, ...]
    task_specific: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lens_id",
            _validate_token(self.lens_id, "lens_id", max_length=MAX_LENS_ID_LENGTH),
        )
        object.__setattr__(
            self,
            "capabilities",
            _normalize_capabilities(self.capabilities, field_name="capabilities"),
        )
        if not isinstance(self.task_specific, bool):
            raise ExecutionFabricError("task_specific must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens_id,
            "capabilities": list(self.capabilities),
            "task_specific": self.task_specific,
        }


@dataclass(frozen=True, slots=True)
class LensRegistry:
    """Immutable lens snapshot with deterministic capability selection."""

    lenses: Mapping[str, ReviewLens] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot = dict(self.lenses)
        for key, lens in snapshot.items():
            if not isinstance(lens, ReviewLens):
                raise ExecutionFabricError("lenses must map IDs to ReviewLens values")
            if key != lens.lens_id:
                raise ExecutionFabricError(
                    f"lens mapping key {key!r} does not match lens_id {lens.lens_id!r}"
                )
        object.__setattr__(self, "lenses", MappingProxyType(snapshot))

    def get(self, lens_id: str) -> ReviewLens | None:
        return self.lenses.get(lens_id)

    def resolve(self, lens_id: str) -> ReviewLens:
        lens = self.get(lens_id)
        if lens is None:
            raise LensNotFoundError(f"no review lens registered for {lens_id!r}")
        return lens

    def register(self, lens: ReviewLens) -> "LensRegistry":
        if not isinstance(lens, ReviewLens):
            raise ExecutionFabricError("lens must be a ReviewLens")
        existing = self.lenses.get(lens.lens_id)
        if existing is not None:
            if existing == lens:
                return self
            raise ExecutionFabricError(
                f"duplicate lens_id {lens.lens_id!r} with conflicting definition"
            )
        updated = dict(self.lenses)
        updated[lens.lens_id] = lens
        return LensRegistry(lenses=updated)

    def register_many(self, lenses: Iterable[ReviewLens]) -> "LensRegistry":
        result = self
        for lens in lenses:
            result = result.register(lens)
        return result

    def select(self, *, capabilities: Iterable[str] = ()) -> tuple[ReviewLens, ...]:
        required = set(
            _normalize_capabilities(capabilities, field_name="capabilities")
            if capabilities
            else ()
        )
        selected = (
            lens
            for lens in self.lenses.values()
            if required.issubset(lens.capabilities)
        )
        return tuple(sorted(selected, key=lambda lens: lens.lens_id))

    def lens_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.lenses))

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": LENS_REGISTRY_PROTOCOL,
            "lenses": {
                lens_id: self.lenses[lens_id].to_dict()
                for lens_id in self.lens_ids()
            },
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"


DEFAULT_LENSES: tuple[ReviewLens, ...] = (
    ReviewLens("architecture", ("architecture", "review")),
    ReviewLens("implementation", ("implementation", "review")),
    ReviewLens(
        "security-reliability",
        ("reliability", "review", "security"),
    ),
    ReviewLens("testing-evidence", ("evidence", "review", "testing")),
)
BUILTIN_LENS_IDS: tuple[str, ...] = tuple(sorted(lens.lens_id for lens in DEFAULT_LENSES))


def build_default_lens_registry() -> LensRegistry:
    """Return a fresh default registry; no global mutable registry is used."""

    return LensRegistry().register_many(DEFAULT_LENSES)
