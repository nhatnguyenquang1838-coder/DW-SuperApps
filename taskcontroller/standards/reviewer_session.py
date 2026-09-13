"""TC-MBX-601 hardening: isolated first-pass reviewer sessions.

This module allocates deterministic reviewer/session identities around one exact
TaskContextPack.  It is a provider-neutral evidence boundary: first-pass
payloads contain source and standards references/digests, never peer findings,
conversation history, or provider output.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.standards.context_pack import TaskContextPack


REVIEWER_SESSION_PROTOCOL = "dw.taskcontroller.reviewer-session/v1"
INITIAL_FIRST_PASS = "INITIAL_FIRST_PASS"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_MAX_IDENTIFIER_LENGTH = 128
_MAX_LENS_LENGTH = 128
_FORBIDDEN_PEER_FIELDS = frozenset(
    {
        "peer_findings",
        "peer_finding_refs",
        "peer_conclusions",
        "peer_reviews",
        "reviewer_findings",
        "reviewer_conclusions",
        "transcript",
        "conversation_history",
    }
)


class ReviewerSessionError(TaskControllerValidationError):
    """Stable fail-closed error for reviewer-session construction."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReviewerSessionError(
            "REVIEWER_SESSION_NOT_SERIALIZABLE",
            f"session payload is not canonical JSON: {type(exc).__name__}",
        ) from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identifier(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_IDENTIFIER_LENGTH
        or not _IDENTIFIER_RE.fullmatch(value)
    ):
        raise ReviewerSessionError(
            "REVIEWER_SESSION_INVALID",
            f"{field} must be a stable identifier of at most {_MAX_IDENTIFIER_LENGTH} characters",
        )
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_LENS_LENGTH:
        raise ReviewerSessionError(
            "REVIEWER_SESSION_INVALID",
            f"{field} must be non-empty text of at most {_MAX_LENS_LENGTH} characters",
        )
    return value


def _digest_field(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ReviewerSessionError(
            "REVIEWER_SESSION_INVALID",
            f"{field} must be sha256:<64 lowercase hex>",
        )
    return value


def _copy_refs(values: Sequence[Mapping[str, Any]], field: str) -> tuple[dict[str, Any], ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise ReviewerSessionError("REVIEWER_CONTEXT_INVALID", f"{field} must be a sequence")
    try:
        copied = tuple(copy.deepcopy(dict(value)) for value in values)
    except (TypeError, ValueError) as exc:
        raise ReviewerSessionError(
            "REVIEWER_CONTEXT_INVALID", f"{field} contains a non-object reference"
        ) from exc
    if not copied:
        raise ReviewerSessionError("REVIEWER_CONTEXT_INVALID", f"{field} must not be empty")
    return copied


def _sorted_refs(values: Sequence[Mapping[str, Any]], field: str) -> tuple[dict[str, Any], ...]:
    copied = _copy_refs(values, field)
    try:
        return tuple(
            sorted(
                copied,
                key=lambda item: _canonical_bytes(item),
            )
        )
    except ReviewerSessionError:
        raise


def _forbidden_peer_input(value: Any) -> bool:
    return value is not None and value != () and value != [] and value != ""


@dataclass(frozen=True, slots=True)
class ReviewerSpec:
    """One reviewer identity/lens pair for the independent first pass."""

    reviewer_id: str
    lens: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewer_id", _identifier(self.reviewer_id, "reviewer_id"))
        object.__setattr__(self, "lens", _text(self.lens, "lens"))

    @classmethod
    def from_value(cls, value: "ReviewerSpec | Mapping[str, Any]") -> "ReviewerSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ReviewerSessionError(
                "REVIEWER_SPEC_INVALID", "reviewer spec must be an object"
            )
        candidate = dict(value)
        if _FORBIDDEN_PEER_FIELDS.intersection(candidate):
            raise ReviewerSessionError(
                "REVIEWER_PEER_INPUT_FORBIDDEN",
                "reviewer spec cannot carry peer findings or conclusions",
            )
        if set(candidate) != {"reviewer_id", "lens"}:
            raise ReviewerSessionError(
                "REVIEWER_SPEC_INVALID",
                "reviewer spec must contain only reviewer_id and lens",
            )
        try:
            return cls(reviewer_id=candidate["reviewer_id"], lens=candidate["lens"])
        except KeyError as exc:
            raise ReviewerSessionError(
                "REVIEWER_SPEC_INVALID", "reviewer_id and lens are required"
            ) from exc

    def to_dict(self) -> dict[str, str]:
        return {"reviewer_id": self.reviewer_id, "lens": self.lens}


@dataclass(frozen=True, slots=True)
class ReviewerSession:
    """Immutable first-pass session envelope for one reviewer."""

    run_id: str
    node_id: str
    attempt_id: str
    reviewer_id: str
    lens: str
    session_id: str
    context_id: str
    source_pack_digest: str
    standards_profile_digest: str
    standards_context_digest: str
    standards_materialization_digest: str
    source_refs: tuple[dict[str, Any], ...]
    standards_source_refs: tuple[dict[str, Any], ...]
    context_digest: str
    session_digest: str
    peer_finding_refs: tuple[str, ...] = ()
    phase: str = INITIAL_FIRST_PASS

    def __post_init__(self) -> None:
        for field in ("run_id", "node_id", "attempt_id", "reviewer_id", "session_id", "context_id"):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        object.__setattr__(self, "lens", _text(self.lens, "lens"))
        if self.phase != INITIAL_FIRST_PASS:
            raise ReviewerSessionError(
                "REVIEWER_SESSION_INVALID", "first-pass session phase is fixed"
            )
        for field in (
            "source_pack_digest",
            "standards_profile_digest",
            "standards_context_digest",
            "standards_materialization_digest",
            "context_digest",
            "session_digest",
        ):
            object.__setattr__(self, field, _digest_field(getattr(self, field), field))
        object.__setattr__(
            self,
            "source_refs",
            _sorted_refs(self.source_refs, "source_refs"),
        )
        object.__setattr__(
            self,
            "standards_source_refs",
            _sorted_refs(self.standards_source_refs, "standards_source_refs"),
        )
        if self.peer_finding_refs:
            raise ReviewerSessionError(
                "REVIEWER_PEER_INPUT_FORBIDDEN",
                "first-pass sessions cannot carry peer finding references",
            )
        object.__setattr__(self, "peer_finding_refs", ())

    def _payload(self) -> dict[str, Any]:
        return {
            "protocol": REVIEWER_SESSION_PROTOCOL,
            "phase": self.phase,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "session_id": self.session_id,
            "context_id": self.context_id,
            "reviewer": {"reviewer_id": self.reviewer_id, "lens": self.lens},
            "source_binding": {
                "inventory_digest": self.source_pack_digest,
                "refs": copy.deepcopy(list(self.source_refs)),
            },
            "standards_binding": {
                "profile_digest": self.standards_profile_digest,
                "context_digest": self.standards_context_digest,
                "materialization_digest": self.standards_materialization_digest,
                "source_refs": copy.deepcopy(list(self.standards_source_refs)),
            },
            "peer_finding_refs": [],
            "context_digest": self.context_digest,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive, machine-readable session envelope."""

        payload = self._payload()
        payload["session_digest"] = self.session_digest
        return payload

    def first_pass_context(self) -> dict[str, Any]:
        """Return the exact context supplied before any reviewer conclusions."""

        return copy.deepcopy(self.to_dict())


class ReviewerSessionFactory:
    """Allocate isolated deterministic reviewer sessions from one bound pack."""

    def create(
        self,
        *,
        run_id: str,
        node_id: str,
        attempt_id: str,
        task_context: TaskContextPack,
        reviewers: Sequence[ReviewerSpec | Mapping[str, Any]],
        peer_finding_refs: Sequence[str] | None = None,
    ) -> tuple[ReviewerSession, ...]:
        run_id = _identifier(run_id, "run_id")
        node_id = _identifier(node_id, "node_id")
        attempt_id = _identifier(attempt_id, "attempt_id")
        if not isinstance(task_context, TaskContextPack):
            raise ReviewerSessionError(
                "REVIEWER_CONTEXT_INVALID", "task_context must be a TaskContextPack"
            )
        if not task_context.sources:
            raise ReviewerSessionError(
                "REVIEWER_CONTEXT_INVALID", "task context must bind at least one source"
            )
        if _forbidden_peer_input(peer_finding_refs):
            raise ReviewerSessionError(
                "REVIEWER_PEER_INPUT_FORBIDDEN",
                "peer findings/conclusions cannot enter first-pass allocation",
            )
        if isinstance(reviewers, (str, bytes, bytearray)):
            raise ReviewerSessionError(
                "REVIEWER_SPEC_INVALID", "reviewers must be a sequence of specs"
            )
        try:
            specs = tuple(ReviewerSpec.from_value(value) for value in reviewers)
        except TypeError as exc:
            raise ReviewerSessionError(
                "REVIEWER_SPEC_INVALID", "reviewers must be iterable"
            ) from exc
        if not specs:
            raise ReviewerSessionError(
                "REVIEWER_SPEC_INVALID", "at least one reviewer is required"
            )
        reviewer_ids = [spec.reviewer_id for spec in specs]
        if len(set(reviewer_ids)) != len(reviewer_ids):
            raise ReviewerSessionError(
                "REVIEWER_IDENTITY_COLLISION",
                "each reviewer receives exactly one first-pass session",
            )

        receipt = task_context.standards.receipt
        source_refs = tuple(item.source.to_dict() for item in task_context.sources)
        standards_source_refs = tuple(source.to_dict() for source in receipt.sources)
        source_binding = {
            "inventory_digest": task_context.inventory_digest,
            "refs": list(_sorted_refs(source_refs, "source_refs")),
        }
        standards_binding = {
            "profile_id": receipt.profile_id,
            "version": receipt.version,
            "profile_digest": receipt.digest,
            "context_digest": receipt.context_digest,
            "materialization_digest": receipt.materialization_digest,
            "source_refs": list(_sorted_refs(standards_source_refs, "standards_source_refs")),
        }

        sessions: list[ReviewerSession] = []
        for spec in sorted(specs, key=lambda item: (item.reviewer_id, item.lens)):
            context_identity = {
                "protocol": REVIEWER_SESSION_PROTOCOL,
                "phase": INITIAL_FIRST_PASS,
                "run_id": run_id,
                "node_id": node_id,
                "attempt_id": attempt_id,
                "reviewer": spec.to_dict(),
                "source_binding": source_binding,
                "standards_binding": standards_binding,
                "peer_finding_refs": [],
            }
            context_digest = _digest(context_identity)
            context_id = "context-" + hashlib.sha256(
                _canonical_bytes(context_identity)
            ).hexdigest()[:32]
            session_identity = {
                "context_id": context_id,
                "run_id": run_id,
                "node_id": node_id,
                "attempt_id": attempt_id,
                "reviewer_id": spec.reviewer_id,
            }
            session_id = "session-" + hashlib.sha256(
                _canonical_bytes(session_identity)
            ).hexdigest()[:32]
            session_payload = {
                **context_identity,
                "session_id": session_id,
                "context_id": context_id,
                "context_digest": context_digest,
            }
            session_digest = _digest(session_payload)
            sessions.append(
                ReviewerSession(
                    run_id=run_id,
                    node_id=node_id,
                    attempt_id=attempt_id,
                    reviewer_id=spec.reviewer_id,
                    lens=spec.lens,
                    session_id=session_id,
                    context_id=context_id,
                    source_pack_digest=task_context.inventory_digest,
                    standards_profile_digest=receipt.digest,
                    standards_context_digest=receipt.context_digest,
                    standards_materialization_digest=receipt.materialization_digest,
                    source_refs=source_binding["refs"],
                    standards_source_refs=standards_binding["source_refs"],
                    context_digest=context_digest,
                    session_digest=session_digest,
                )
            )
        return tuple(sessions)

    def create_sessions(self, **kwargs: Any) -> tuple[ReviewerSession, ...]:
        """Compatibility alias for callers that name the operation explicitly."""

        return self.create(**kwargs)

    def build(self, **kwargs: Any) -> tuple[ReviewerSession, ...]:
        """Compatibility alias for the factory's bounded build operation."""

        return self.create(**kwargs)


def create_reviewer_sessions(
    **kwargs: Any,
) -> tuple[ReviewerSession, ...]:
    """Functional entry point for deterministic isolated first-pass sessions."""

    return ReviewerSessionFactory().create(**kwargs)


__all__ = [
    "INITIAL_FIRST_PASS",
    "REVIEWER_SESSION_PROTOCOL",
    "ReviewerSession",
    "ReviewerSessionError",
    "ReviewerSessionFactory",
    "ReviewerSpec",
    "create_reviewer_sessions",
]
