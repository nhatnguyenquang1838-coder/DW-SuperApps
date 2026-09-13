"""TC-MBX-801 hardening: one authoritative generation/fence predicate.

This module is pure and provider-neutral.  It never mutates a candidate,
current-attempt record, mailbox, or runtime state.  A rejected candidate is
classified as historical evidence; malformed identity is a fail-closed schema
error.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, NoReturn


_REQUIRED_FIELDS = (
    "run_id",
    "node_id",
    "attempt_id",
    "lease_generation",
    "fencing_token",
)
_OPTIONAL_SCOPE_FIELDS = ("execution_id",)


class GenerationFenceDisposition(str, Enum):
    """Machine disposition for a candidate state-advancing write."""

    ACCEPTED = "ACCEPTED"
    STALE_RESULT = "STALE_RESULT"


class GenerationFenceError(ValueError):
    """Fail-closed error for malformed generation/fence identity."""

    def __init__(self, code: str, message: str, *, failed_checks: tuple[str, ...] = ()) -> None:
        self.code = code
        self.failed_checks = tuple(failed_checks)
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class GenerationFenceDecision:
    """Pure current-generation acceptance result."""

    disposition: str
    advances_state: bool
    evidence_only: bool
    failed_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.disposition == GenerationFenceDisposition.ACCEPTED.value:
            if not self.advances_state or self.evidence_only or self.failed_checks:
                raise ValueError("accepted generation fence must advance without failed checks")
        elif self.disposition == GenerationFenceDisposition.STALE_RESULT.value:
            if self.advances_state or not self.evidence_only or not self.failed_checks:
                raise ValueError("stale generation fence must be evidence-only")
        else:
            raise ValueError(f"unsupported generation fence disposition: {self.disposition!r}")


def _fail(code: str, message: str, *, failed_checks: tuple[str, ...] = ()) -> NoReturn:
    raise GenerationFenceError(code, message, failed_checks=failed_checks)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        _fail("SCHEMA_INVALID", f"{field} must be a non-empty text value")
    return value.strip()


def _generation(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("SCHEMA_INVALID", f"{field} must be a non-negative integer")
    return value


def _identity(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("SCHEMA_INVALID", f"{name} must be an object")
    candidate = dict(value)
    missing = tuple(field for field in _REQUIRED_FIELDS if field not in candidate)
    if missing:
        _fail("SCHEMA_INVALID", f"{name} is missing: {', '.join(missing)}", failed_checks=missing)
    normalized = {
        "run_id": _text(candidate["run_id"], f"{name}.run_id"),
        "node_id": _text(candidate["node_id"], f"{name}.node_id"),
        "attempt_id": _text(candidate["attempt_id"], f"{name}.attempt_id"),
        "lease_generation": _generation(candidate["lease_generation"], f"{name}.lease_generation"),
        "fencing_token": _text(candidate["fencing_token"], f"{name}.fencing_token"),
    }
    if "execution_id" in candidate and candidate["execution_id"] is not None:
        normalized["execution_id"] = _text(candidate["execution_id"], f"{name}.execution_id")
    return normalized


def evaluate_generation_fence(
    candidate: Mapping[str, Any],
    current: Mapping[str, Any],
) -> GenerationFenceDecision:
    """Evaluate one candidate against the authoritative current attempt.

    The shared identity is the parent/child/Mixer minimum tuple
    ``(run_id, node_id, attempt_id, lease_generation, fencing_token)``.  When
    both sides expose ``execution_id``, it is also compared as an exact scope
    binding.  Older generations and foreign fences are accepted only as
    historical evidence and can never advance semantic state.
    """

    actual = _identity(candidate, "candidate")
    expected = _identity(current, "current")
    failed: list[str] = []
    for field in _REQUIRED_FIELDS + _OPTIONAL_SCOPE_FIELDS:
        if field not in actual or field not in expected:
            continue
        if actual[field] != expected[field]:
            failed.append(field)
    if failed:
        return GenerationFenceDecision(
            disposition=GenerationFenceDisposition.STALE_RESULT.value,
            advances_state=False,
            evidence_only=True,
            failed_checks=tuple(failed),
        )
    return GenerationFenceDecision(
        disposition=GenerationFenceDisposition.ACCEPTED.value,
        advances_state=True,
        evidence_only=False,
    )


def require_current_generation(
    candidate: Mapping[str, Any],
    current: Mapping[str, Any],
) -> None:
    """Raise a typed stale error when a caller requires advancement."""

    decision = evaluate_generation_fence(candidate, current)
    if not decision.advances_state:
        _fail(
            "STALE_GENERATION",
            "candidate is not bound to the current attempt generation/fence",
            failed_checks=decision.failed_checks,
        )


__all__ = [
    "GenerationFenceDecision",
    "GenerationFenceDisposition",
    "GenerationFenceError",
    "evaluate_generation_fence",
    "require_current_generation",
]
