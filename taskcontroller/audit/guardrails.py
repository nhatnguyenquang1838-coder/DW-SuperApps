from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    reason: str = ""
    detail: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.detail is None:
            object.__setattr__(self, "detail", {})

    def to_dict(self) -> dict[str, Any]:
        return {"blocked": self.blocked, "reason": self.reason, "detail": self.detail or {}}


# Pure pre-checks — no external imports, no state mutation.
# ---------------------------------------------------------------------------


def check_terminal(run_status: str) -> GuardrailResult:
    """Fail-closed: terminal runs must not allow new external actions."""
    terminal = {"COMPLETED", "FAILED", "CANCELLED"}
    if run_status in terminal:
        return GuardrailResult(
            blocked=True,
            reason="run_terminal",
            detail={"status": run_status},
        )
    return GuardrailResult(blocked=False)


def check_duplicate_root(existing_root: str | None, proposed_root: str) -> GuardrailResult:
    """Fail-closed: binding registry must not be asked to create a second root."""
    if existing_root is not None and existing_root != proposed_root:
        return GuardrailResult(
            blocked=True,
            reason="duplicate_root",
            detail={"existing_root": existing_root, "proposed_root": proposed_root},
        )
    return GuardrailResult(blocked=False)


def check_authority(authority_ref: str, expected: str) -> GuardrailResult:
    """Pure string comparison — real authority verification lives at the
    orchestration layer; this guardrail only surfaces a mismatch."""
    if authority_ref != expected:
        return GuardrailResult(
            blocked=True,
            reason="authority_mismatch",
            detail={"authority_ref": authority_ref, "expected": expected},
        )
    return GuardrailResult(blocked=False)


def check_sha_format(sha: str, field_name: str = "sha") -> GuardrailResult:
    """Fail-closed: reject non-40-char-hex SHA before external call."""
    if not isinstance(sha, str) or len(sha) != 40:
        return GuardrailResult(
            blocked=True,
            reason=f"invalid_{field_name}_format",
            detail={"value": sha},
        )
    if any(c not in "0123456789abcdef" for c in sha.lower()):
        return GuardrailResult(
            blocked=True,
            reason=f"invalid_{field_name}_hex",
            detail={"value": sha},
        )
    return GuardrailResult(blocked=False)
