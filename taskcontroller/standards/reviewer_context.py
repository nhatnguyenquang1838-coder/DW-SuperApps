"""Independent initial contexts for bounded TaskController reviewers.

This module is intentionally a pure boundary.  It receives one already-bound
``TaskContextPack`` and reviewer-owned findings, then emits a reviewer-specific
first-pass payload.  Peer findings are neither accepted nor serialized.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.standards.context_pack import TaskContextPack


REVIEWER_INITIAL_CONTEXT_PROTOCOL = "dw.taskcontroller.reviewer-initial-context/v1"
_MAX_REVIEWER_ID_LENGTH = 128
_MAX_LENS_LENGTH = 128
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ReviewerContextError(TaskControllerValidationError):
    """Stable fail-closed error for reviewer-context construction."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


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
        raise ReviewerContextError(
            "REVIEWER_CONTEXT_NOT_SERIALIZABLE",
            f"context contains non-canonical JSON data: {exc}",
        ) from exc


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identifier(value: Any, field: str, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or not _IDENTIFIER_RE.fullmatch(value)
    ):
        raise ReviewerContextError(
            "REVIEWER_CONTEXT_INVALID",
            f"{field} must be a stable identifier of at most {limit} characters",
        )
    return value


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ReviewerContextError(
            "REVIEWER_CONTEXT_INVALID",
            f"{field} must be non-empty text of at most {limit} characters",
        )
    return value


def _finding_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        candidate = dict(value)
    elif hasattr(value, "to_dict"):
        candidate = value.to_dict()
        if not isinstance(candidate, Mapping):
            raise ReviewerContextError(
                "REVIEWER_FINDING_INVALID",
                "finding.to_dict() must return an object",
            )
        candidate = dict(candidate)
    else:
        raise ReviewerContextError(
            "REVIEWER_FINDING_INVALID",
            "findings must be mappings or objects with to_dict()",
        )
    try:
        return copy.deepcopy(candidate)
    except (TypeError, ValueError) as exc:
        raise ReviewerContextError(
            "REVIEWER_FINDING_INVALID",
            f"finding cannot be copied safely: {exc}",
        ) from exc


def _normalize_findings(
    reviewer_id: str,
    findings: Sequence[Mapping[str, Any] | Any] | None,
) -> tuple[dict[str, Any], ...]:
    if findings is None:
        return ()
    if isinstance(findings, (str, bytes, bytearray)):
        raise ReviewerContextError(
            "REVIEWER_FINDING_INVALID",
            "findings must be a sequence of finding objects",
        )
    try:
        values = tuple(findings)
    except TypeError as exc:
        raise ReviewerContextError(
            "REVIEWER_FINDING_INVALID",
            "findings must be iterable",
        ) from exc

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for value in values:
        finding = _finding_mapping(value)
        finding_id = _identifier(
            finding.get("finding_id"), "finding_id", _MAX_REVIEWER_ID_LENGTH
        )
        owner = finding.get("reviewer")
        if owner != reviewer_id:
            raise ReviewerContextError(
                "REVIEWER_FINDING_OWNER_MISMATCH",
                f"finding {finding_id} is not owned by {reviewer_id}",
            )
        if finding_id in seen_ids:
            raise ReviewerContextError(
                "REVIEWER_FINDING_DUPLICATE",
                f"finding {finding_id} appears more than once",
            )
        seen_ids.add(finding_id)
        normalized.append(finding)

    try:
        normalized.sort(key=lambda item: (item["finding_id"], _canonical_bytes(item)))
    except ReviewerContextError:
        raise
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class ReviewerInitialContext:
    """One reviewer's isolated, first-pass context."""

    reviewer_id: str
    lens: str
    task_context: TaskContextPack
    own_findings: tuple[dict[str, Any], ...]
    own_findings_digest: str
    context_digest: str

    def __post_init__(self) -> None:
        _identifier(self.reviewer_id, "reviewer_id", _MAX_REVIEWER_ID_LENGTH)
        _text(self.lens, "lens", _MAX_LENS_LENGTH)
        if not isinstance(self.task_context, TaskContextPack):
            raise ReviewerContextError(
                "REVIEWER_CONTEXT_INVALID",
                "task_context must be a TaskContextPack",
            )
        object.__setattr__(
            self,
            "own_findings",
            tuple(copy.deepcopy(item) for item in self.own_findings),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical context sent to this reviewer only."""

        return {
            "protocol": REVIEWER_INITIAL_CONTEXT_PROTOCOL,
            "reviewer": {"reviewer_id": self.reviewer_id, "lens": self.lens},
            "task_context": self.task_context.to_dict(),
            "own_findings": copy.deepcopy(list(self.own_findings)),
            "own_findings_digest": self.own_findings_digest,
            "context_digest": self.context_digest,
        }

    def first_prompt_context(self) -> dict[str, Any]:
        """Return a defensive copy of the reviewer's first prompt context."""

        return copy.deepcopy(self.to_dict())


class ReviewerInitialContextFactory:
    """Build isolated initial contexts without any peer-finding input channel."""

    def build(
        self,
        *,
        reviewer_id: str,
        lens: str,
        task_context: TaskContextPack,
        own_findings: Sequence[Mapping[str, Any] | Any] | None = None,
    ) -> ReviewerInitialContext:
        reviewer_id = _identifier(reviewer_id, "reviewer_id", _MAX_REVIEWER_ID_LENGTH)
        lens = _text(lens, "lens", _MAX_LENS_LENGTH)
        if not isinstance(task_context, TaskContextPack):
            raise ReviewerContextError(
                "REVIEWER_CONTEXT_INVALID",
                "task_context must be a TaskContextPack",
            )

        normalized_findings = _normalize_findings(reviewer_id, own_findings)
        finding_payload = {
            "reviewer_id": reviewer_id,
            "findings": list(normalized_findings),
        }
        own_findings_digest = _digest(finding_payload)
        digest_payload = {
            "protocol": REVIEWER_INITIAL_CONTEXT_PROTOCOL,
            "reviewer": {"reviewer_id": reviewer_id, "lens": lens},
            "task_context": task_context.to_dict(),
            "own_findings": list(normalized_findings),
            "own_findings_digest": own_findings_digest,
        }
        return ReviewerInitialContext(
            reviewer_id=reviewer_id,
            lens=lens,
            task_context=task_context,
            own_findings=normalized_findings,
            own_findings_digest=own_findings_digest,
            context_digest=_digest(digest_payload),
        )


def build_reviewer_initial_context(
    *,
    reviewer_id: str,
    lens: str,
    task_context: TaskContextPack,
    own_findings: Sequence[Mapping[str, Any] | Any] | None = None,
) -> ReviewerInitialContext:
    """Functional entry point for one isolated reviewer context."""

    return ReviewerInitialContextFactory().build(
        reviewer_id=reviewer_id,
        lens=lens,
        task_context=task_context,
        own_findings=own_findings,
    )


__all__ = [
    "REVIEWER_INITIAL_CONTEXT_PROTOCOL",
    "ReviewerContextError",
    "ReviewerInitialContext",
    "ReviewerInitialContextFactory",
    "build_reviewer_initial_context",
]
