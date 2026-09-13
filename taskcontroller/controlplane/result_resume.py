"""TC-MBX-703: Controller polling/resume from canonical mailbox/v2 results.

This module is a provider-neutral Controller boundary.  It consumes only
append-only mailbox events newer than a durable actor cursor, validates the
complete current execution binding before returning a terminal result, and
records rejected/foreign observations without turning them into semantic
progress.  Slack, GitHub transport and runtime workers remain outside this
boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.controlplane.lease_binding import (
    LeaseBindingError,
    LeaseFenceDecision,
    evaluate_result_fence,
)
from taskcontroller.domain.models import WorkLease
from taskcontroller.execution.terminal_result import (
    TerminalParentResult,
    TerminalResultError,
)
from taskcontroller.interaction.mailbox_repository import (
    MailboxActorCursor,
    MailboxEvent,
    MailboxRepository,
)
from taskcontroller.interaction.mailbox_v2 import canonical_digest


POLL_RESULT_AVAILABLE = "RESULT_AVAILABLE"
POLL_NO_NEW_RESULT = "NO_NEW_RESULT"
_TERMINAL_MESSAGE_TYPE = "terminal_result"
_REQUIRED_IDENTITY_FIELDS = (
    "run_id",
    "node_id",
    "plan_version",
    "contract_digest",
    "boundary_digest",
    "attempt_id",
    "lease_generation",
    "fencing_token",
    "source_digest",
)
_ACTIVE_LEASE_UNSET = object()


class ControllerResultResumeError(TaskControllerValidationError):
    """Stable fail-closed error for Controller result polling."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise ControllerResultResumeError(code, message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("RESUME_BINDING_INVALID", f"{field} must be a non-empty string")
    if "\x00" in value:
        _fail("RESUME_BINDING_INVALID", f"{field} must not contain NUL")
    return value.strip()


def _validate_binding(
    cursor: MailboxActorCursor,
    *,
    correlation_id: str,
    expected_identity: Mapping[str, Any],
    expected_source_digest: str | None,
    expected_standards_digest: str | None,
    expected_result_digest: str | None,
) -> dict[str, Any]:
    if not isinstance(cursor, MailboxActorCursor):
        _fail("RESUME_CURSOR_INVALID", "poll requires a MailboxActorCursor")
    if not isinstance(expected_identity, Mapping):
        _fail("RESUME_IDENTITY_REQUIRED", "expected_identity must be an object")
    identity = dict(expected_identity)
    missing = [field for field in _REQUIRED_IDENTITY_FIELDS if field not in identity]
    if missing:
        _fail(
            "RESUME_IDENTITY_REQUIRED",
            "expected_identity is missing: " + ", ".join(missing),
        )
    if identity["run_id"] != cursor.run_id or identity["node_id"] != cursor.node_id:
        _fail("RESUME_CURSOR_MISMATCH", "cursor run/node differs from current execution identity")
    _text(correlation_id, "correlation_id")
    if expected_source_digest is not None and expected_source_digest != identity["source_digest"]:
        _fail("RESUME_DIGEST_MISMATCH", "expected source digest differs from execution identity")
    if expected_standards_digest is not None:
        _text(expected_standards_digest, "expected_standards_digest")
    if expected_result_digest is not None:
        _text(expected_result_digest, "expected_result_digest")
    return identity


def _verify_event_integrity(event: MailboxEvent) -> None:
    if not isinstance(event, MailboxEvent):
        _fail("RESUME_SCAN_INVALID", "repository returned a non-MailboxEvent")
    envelope_digest = event.envelope.digest()
    if event.envelope_digest != envelope_digest:
        _fail("RESUME_DIGEST_MISMATCH", "event envelope digest differs from canonical envelope")
    if canonical_digest(event.to_dict()) != event.event_digest:
        _fail("RESUME_DIGEST_MISMATCH", "event digest differs from canonical event bytes")
    if event.logical_seq != event.envelope.seq:
        _fail("RESUME_SEQUENCE_MISMATCH", "event logical sequence differs from envelope sequence")


def _identity_matches(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(actual.get(field) == expected[field] for field in _REQUIRED_IDENTITY_FIELDS)


@dataclass(frozen=True, slots=True)
class ControllerResultPoll:
    """Exact result-poll evidence, including ignored mailbox observations."""

    status: str
    cursor: MailboxActorCursor
    terminal_result: TerminalParentResult | None = None
    observed_event_ids: tuple[str, ...] = ()
    ignored_event_ids: tuple[str, ...] = ()
    ignored_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {POLL_RESULT_AVAILABLE, POLL_NO_NEW_RESULT}:
            raise ValueError(f"unsupported Controller result poll status: {self.status!r}")
        if not isinstance(self.cursor, MailboxActorCursor):
            raise ValueError("Controller result poll cursor must be a MailboxActorCursor")
        if self.status == POLL_RESULT_AVAILABLE and self.terminal_result is None:
            raise ValueError("RESULT_AVAILABLE requires a terminal result")
        if self.status == POLL_NO_NEW_RESULT and self.terminal_result is not None:
            raise ValueError("NO_NEW_RESULT cannot carry a terminal result")
        if len(self.ignored_event_ids) != len(self.ignored_reasons):
            raise ValueError("ignored event IDs and reasons must have equal length")



def _ignored(
    ignored_event_ids: list[str],
    ignored_reasons: list[str],
    event: MailboxEvent,
    reason: str,
) -> None:
    ignored_event_ids.append(event.event_id)
    ignored_reasons.append(reason)


def _fence_ignore_reason(decision: LeaseFenceDecision) -> str:
    if "active_lease" in decision.failed_checks:
        return "ACTIVE_FENCE_MISSING"
    if "lease_status" in decision.failed_checks:
        return "ACTIVE_FENCE_INACTIVE"
    if "lease_expiry" in decision.failed_checks:
        return "ACTIVE_FENCE_EXPIRED"
    return "ACTIVE_FENCE_MISMATCH"



def poll_controller_terminal_result(
    repository: MailboxRepository,
    cursor: MailboxActorCursor,
    *,
    correlation_id: str,
    expected_identity: Mapping[str, Any],
    expected_source_digest: str | None = None,
    expected_standards_digest: str | None = None,
    expected_result_digest: str | None = None,
    active_lease: WorkLease | None | object = _ACTIVE_LEASE_UNSET,
    lease_now: str | None = None,
) -> ControllerResultPoll:
    """Poll only newer executor events and resume from one exact current result.

    Non-current terminal events remain in the append-only mailbox and are
    returned as ignored evidence.  They never become a Controller result.  The
    durable cursor advances over every valid observed event only after the
    complete bounded scan has finished; a failed cursor acknowledgement raises
    instead of returning a possibly reprocessed semantic result.
    """

    if not isinstance(repository, MailboxRepository):
        _fail("RESUME_REPOSITORY_INVALID", "poll requires a MailboxRepository")
    identity = _validate_binding(
        cursor,
        correlation_id=correlation_id,
        expected_identity=expected_identity,
        expected_source_digest=expected_source_digest,
        expected_standards_digest=expected_standards_digest,
        expected_result_digest=expected_result_digest,
    )
    expected_correlation = _text(correlation_id, "correlation_id")
    events = repository.scan_after_cursor(cursor)
    if not isinstance(events, tuple):
        _fail("RESUME_SCAN_INVALID", "repository cursor scan must return a tuple")

    observed_event_ids: list[str] = []
    ignored_event_ids: list[str] = []
    ignored_reasons: list[str] = []
    next_cursor = cursor
    selected: TerminalParentResult | None = None

    for event in sorted(events, key=lambda item: item.event_seq):
        _verify_event_integrity(event)
        observed_event_ids.append(event.event_id)
        if (
            event.mailbox_ref != cursor.mailbox_ref
            or event.producer_namespace != cursor.actor_namespace
            or event.envelope.run_id != cursor.run_id
            or event.envelope.node_id != cursor.node_id
        ):
            _ignored(ignored_event_ids, ignored_reasons, event, "FOREIGN_EVENT")
            continue
        if event.event_seq <= cursor.last_event_seq or event.logical_seq <= cursor.last_logical_seq:
            _fail("RESUME_SEQUENCE_MISMATCH", "cursor scan returned an event that is not newer")
        next_cursor = next_cursor.observe(event)
        payload = event.envelope.to_dict()
        if payload.get("message_type") != _TERMINAL_MESSAGE_TYPE:
            _ignored(ignored_event_ids, ignored_reasons, event, "NON_TERMINAL_EVENT")
            continue

        try:
            candidate = TerminalParentResult.from_envelope(event.envelope)
        except TerminalResultError:
            _ignored(ignored_event_ids, ignored_reasons, event, "INVALID_TERMINAL_RESULT")
            continue

        if payload.get("correlation_id") != expected_correlation:
            _ignored(ignored_event_ids, ignored_reasons, event, "CORRELATION_MISMATCH")
            continue
        if not _identity_matches(candidate.envelope.execution_identity, identity):
            _ignored(ignored_event_ids, ignored_reasons, event, "EXECUTION_IDENTITY_MISMATCH")
            continue

        if active_lease is not _ACTIVE_LEASE_UNSET:
            if active_lease is not None and not isinstance(active_lease, WorkLease):
                _fail("RESUME_LEASE_BINDING_INVALID", "active_lease must be a WorkLease or None")
            current_lease = active_lease if isinstance(active_lease, WorkLease) else None
            try:
                fence = evaluate_result_fence(event.envelope, current_lease, now=lease_now)
            except LeaseBindingError as exc:
                _fail("RESUME_LEASE_BINDING_INVALID", str(exc))
            if not fence.advances_state:
                _ignored(ignored_event_ids, ignored_reasons, event, _fence_ignore_reason(fence))
                continue

        candidate_payload = candidate.envelope.to_dict()
        standards_profile = candidate_payload.get("standards_profile", {})
        terminal_payload = candidate_payload.get("payload", {})
        if (
            not isinstance(standards_profile, Mapping)
            or not isinstance(terminal_payload, Mapping)
            or standards_profile.get("digest") != terminal_payload.get("standards_digest")
        ):
            _ignored(ignored_event_ids, ignored_reasons, event, "STANDARDS_DIGEST_MISMATCH")
            continue
        if (
            expected_standards_digest is not None
            and standards_profile.get("digest") != expected_standards_digest
        ):
            _ignored(ignored_event_ids, ignored_reasons, event, "STANDARDS_DIGEST_MISMATCH")
            continue
        if (
            expected_source_digest is not None
            and candidate_payload.get("source_manifest", {}).get("digest") != expected_source_digest
        ):
            _ignored(ignored_event_ids, ignored_reasons, event, "SOURCE_DIGEST_MISMATCH")
            continue
        if expected_result_digest is not None and candidate.result_digest != expected_result_digest:
            _ignored(ignored_event_ids, ignored_reasons, event, "RESULT_DIGEST_MISMATCH")
            continue

        if selected is not None and selected.result_digest != candidate.result_digest:
            _fail(
                "TERMINAL_RESULT_CONFLICT",
                "multiple current terminal results have different result digests",
            )
        selected = candidate

    if next_cursor != cursor:
        acknowledged = repository.acknowledge_cursor(next_cursor)
        if acknowledged != next_cursor:
            _fail("RESUME_DIGEST_MISMATCH", "durable cursor readback differs from observed cursor")
        next_cursor = acknowledged

    return ControllerResultPoll(
        status=POLL_RESULT_AVAILABLE if selected is not None else POLL_NO_NEW_RESULT,
        cursor=next_cursor,
        terminal_result=selected,
        observed_event_ids=tuple(observed_event_ids),
        ignored_event_ids=tuple(ignored_event_ids),
        ignored_reasons=tuple(ignored_reasons),
    )


# Explicit alias for callers naming the operation by its recovery consequence.
resume_controller_from_mailbox = poll_controller_terminal_result


__all__ = [
    "ControllerResultPoll",
    "ControllerResultResumeError",
    "POLL_NO_NEW_RESULT",
    "POLL_RESULT_AVAILABLE",
    "poll_controller_terminal_result",
    "resume_controller_from_mailbox",
]
