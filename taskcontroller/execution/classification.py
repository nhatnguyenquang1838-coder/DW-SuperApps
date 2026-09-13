"""TC-MBX-501 bounded execution-classification metadata.

This module defines the normalized output boundary for the future classifier. It
is deliberately metadata-only: it does not infer a class, create child work,
dispatch agents, or persist prompts/conversation transcripts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from taskcontroller.errors import TaskControllerValidationError


CLASSIFICATION_SCHEMA_VERSION = "dw.taskcontroller.execution-classification/v1"
MAX_RATIONALE_LENGTH = 512
MAX_LENSES = 16
MAX_LENS_LENGTH = 64
MAX_PROPOSED_CHILD_COUNT = 64
MAX_JOIN_POLICY_LENGTH = 64
MAX_PRECONDITIONS = 16
MAX_PRECONDITION_LENGTH = 256


class ExecutionClass(str, Enum):
    """Normalized execution shape emitted by a classifier."""

    ATOMIC = "ATOMIC"
    COMPLEX = "COMPLEX"
    REVIEW = "REVIEW"
    CROSS_REVIEW = "CROSS_REVIEW"


_SERIALIZED_FIELDS = frozenset(
    {
        "classification",
        "rationale",
        "lenses",
        "proposed_child_count",
        "join_policy",
        "unresolved_preconditions",
    }
)


def _error(message: str) -> TaskControllerValidationError:
    return TaskControllerValidationError(message)


def _bounded_text(name: str, value: Any, limit: int) -> str:
    if not isinstance(value, str):
        raise _error(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise _error(f"{name} must be non-empty")
    if "\x00" in normalized:
        raise _error(f"{name} must not contain NUL characters")
    if len(normalized.encode("utf-8")) > limit:
        raise _error(f"{name} exceeds {limit} UTF-8 bytes")
    return normalized


def _identifier(name: str, value: Any, limit: int) -> str:
    normalized = _bounded_text(name, value, limit)
    if any(character.isspace() or ord(character) < 0x20 for character in normalized):
        raise _error(f"{name} must be a single identifier")
    return normalized


def _bounded_items(
    name: str,
    values: Any,
    *,
    max_items: int,
    item_limit: int,
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise _error(f"{name} must be an array")
    if len(values) > max_items:
        raise _error(f"{name} exceeds maximum item count {max_items}")
    normalized = tuple(
        _bounded_text(f"{name}[{index}]", item, item_limit)
        for index, item in enumerate(values)
    )
    if len(set(normalized)) != len(normalized):
        raise _error(f"{name} must not contain duplicates")
    # These fields are sets of required metadata, not an ordered transcript.
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class ExecutionClassification:
    """Immutable, bounded classification metadata.

    ``lenses`` and ``unresolved_preconditions`` are normalized to sorted tuples
    and are returned as fresh lists by ``to_dict``. No arbitrary metadata field
    is accepted, which prevents raw prompts, messages, or hidden reasoning from
    becoming part of the persisted classification contract.
    """

    classification: str
    rationale: str
    lenses: tuple[str, ...] = ()
    proposed_child_count: int = 0
    join_policy: str = "NONE"
    unresolved_preconditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            kind = ExecutionClass(self.classification)
        except (TypeError, ValueError):
            values = ", ".join(item.value for item in ExecutionClass)
            raise _error(
                f"classification must be one of {values}"
            ) from None
        object.__setattr__(self, "classification", kind.value)
        object.__setattr__(
            self,
            "rationale",
            _bounded_text("rationale", self.rationale, MAX_RATIONALE_LENGTH),
        )
        object.__setattr__(
            self,
            "lenses",
            _bounded_items(
                "lenses",
                self.lenses,
                max_items=MAX_LENSES,
                item_limit=MAX_LENS_LENGTH,
            ),
        )
        if (
            not isinstance(self.proposed_child_count, int)
            or isinstance(self.proposed_child_count, bool)
        ):
            raise _error("proposed_child_count must be an integer")
        if not 0 <= self.proposed_child_count <= MAX_PROPOSED_CHILD_COUNT:
            raise _error(
                f"proposed_child_count must be between 0 and {MAX_PROPOSED_CHILD_COUNT}"
            )
        object.__setattr__(
            self,
            "join_policy",
            _identifier("join_policy", self.join_policy, MAX_JOIN_POLICY_LENGTH),
        )
        object.__setattr__(
            self,
            "unresolved_preconditions",
            _bounded_items(
                "unresolved_preconditions",
                self.unresolved_preconditions,
                max_items=MAX_PRECONDITIONS,
                item_limit=MAX_PRECONDITION_LENGTH,
            ),
        )

        if kind is ExecutionClass.ATOMIC:
            if self.proposed_child_count != 0 or self.join_policy != "NONE":
                raise _error(
                    "ATOMIC classification must have proposed_child_count=0 and join_policy=NONE"
                )
        else:
            if self.proposed_child_count < 1:
                raise _error(
                    "non-ATOMIC classification must propose at least one child"
                )
            if not self.lenses:
                raise _error("non-ATOMIC classification requires at least one lens")
            if self.join_policy == "NONE":
                raise _error("non-ATOMIC classification requires a join policy")

    @property
    def required_lenses(self) -> tuple[str, ...]:
        """Compatibility/readability alias for the canonical ``lenses`` field."""

        return self.lenses

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionClassification":
        """Deserialize one strict canonical classification mapping."""

        if not isinstance(payload, Mapping):
            raise _error("execution classification must be an object")
        keys = set(payload)
        missing = sorted(_SERIALIZED_FIELDS - keys)
        if missing:
            raise _error("missing fields: " + ", ".join(missing))
        unknown = sorted(keys - _SERIALIZED_FIELDS)
        if unknown:
            raise _error("unsupported fields: " + ", ".join(unknown))
        return cls(
            classification=payload["classification"],
            rationale=payload["rationale"],
            lenses=payload["lenses"],
            proposed_child_count=payload["proposed_child_count"],
            join_policy=payload["join_policy"],
            unresolved_preconditions=payload["unresolved_preconditions"],
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionClassification":
        """Deserialize canonical data, accepting ``required_lenses`` as an alias."""

        if not isinstance(payload, Mapping):
            raise _error("execution classification must be an object")
        candidate = dict(payload)
        if "required_lenses" in candidate:
            if "lenses" in candidate and candidate["lenses"] != candidate["required_lenses"]:
                raise _error("conflicting values for lenses and required_lenses")
            candidate["lenses"] = candidate.pop("required_lenses")
        return cls.from_dict(candidate)

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive JSON-compatible representation."""

        return {
            "classification": self.classification,
            "rationale": self.rationale,
            "lenses": list(self.lenses),
            "proposed_child_count": self.proposed_child_count,
            "join_policy": self.join_policy,
            "unresolved_preconditions": list(self.unresolved_preconditions),
        }

    def canonical_bytes(self) -> bytes:
        """Return deterministic UTF-8 JSON bytes for persistence/digesting."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def digest(self) -> str:
        """Return the stable digest of the normalized metadata."""

        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()


__all__ = [
    "CLASSIFICATION_SCHEMA_VERSION",
    "MAX_RATIONALE_LENGTH",
    "MAX_LENSES",
    "MAX_LENS_LENGTH",
    "MAX_PROPOSED_CHILD_COUNT",
    "MAX_JOIN_POLICY_LENGTH",
    "MAX_PRECONDITIONS",
    "MAX_PRECONDITION_LENGTH",
    "ExecutionClass",
    "ExecutionClassification",
]
