"""TC-MBX-108 universal state-advancing write predicate.

The predicate is transport-neutral and deliberately does not persist or mutate
state.  Callers retain rejected envelopes as historical evidence and advance
current state only for an ``ACCEPTED`` decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, NoReturn, Optional, Union

from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
)


EnvelopeInput = Union[V2MailboxEnvelope, Mapping[str, Any]]


class StateAdvancingDisposition(str, Enum):
    """Machine dispositions for a candidate state-advancing write."""

    ACCEPTED = "ACCEPTED"
    STALE_RESULT = MailboxV2ErrorCode.STALE_RESULT


class StateAdvancingWriteKind(str, Enum):
    """The three v2 writes that may advance current execution state."""

    CHILD_RESULT = "child_result"
    MIXER_RESULT = "mixer_result"
    PARENT_TERMINAL = "terminal_result"

    # Short aliases keep the API readable without changing wire values.
    CHILD = "child_result"
    MIXER = "mixer_result"
    TERMINAL = "terminal_result"


@dataclass(frozen=True)
class StateAdvancingWriteDecision:
    """Pure decision returned by the universal acceptance predicate.

    ``STALE_RESULT`` is intentionally a successful classification rather than
    an exception: the caller can retain the original envelope as evidence while
    proving that no current state advancement was allowed.
    """

    write_kind: str
    disposition: str
    advances_state: bool
    evidence_only: bool
    envelope_digest: str
    failed_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.disposition == StateAdvancingDisposition.ACCEPTED.value:
            if not self.advances_state or self.evidence_only or self.failed_checks:
                raise ValueError("ACCEPTED decision must advance state without failed checks")
        elif self.disposition == StateAdvancingDisposition.STALE_RESULT.value:
            if self.advances_state or not self.evidence_only or not self.failed_checks:
                raise ValueError("STALE_RESULT decision must be evidence-only and non-advancing")
        else:
            raise ValueError(f"unsupported state-advancing disposition: {self.disposition!r}")


_KIND_TO_MESSAGE_TYPE = {
    StateAdvancingWriteKind.CHILD_RESULT.value: "child_result",
    StateAdvancingWriteKind.MIXER_RESULT.value: "mixer_result",
    StateAdvancingWriteKind.PARENT_TERMINAL.value: "terminal_result",
    "child": "child_result",
    "mixer": "mixer_result",
    "parent_terminal": "terminal_result",
    "terminal": "terminal_result",
}

_REQUIRED_CURRENT_FIELDS = (
    "run_id",
    "node_id",
    "plan_version",
    "attempt_id",
    "lease_generation",
)


def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _coerce_envelope(envelope: EnvelopeInput) -> V2MailboxEnvelope:
    if isinstance(envelope, V2MailboxEnvelope):
        return envelope
    if isinstance(envelope, Mapping):
        return V2MailboxEnvelope.from_dict(envelope)
    _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "state-advancing write requires a v2 envelope or mapping")


def _canonical_write_kind(write_kind: StateAdvancingWriteKind | str | None) -> tuple[str, str]:
    if isinstance(write_kind, StateAdvancingWriteKind):
        candidate = write_kind.value
    elif isinstance(write_kind, str):
        candidate = write_kind
    else:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "write_kind is required; message_type must not be inferred",
        )
    message_type = _KIND_TO_MESSAGE_TYPE.get(candidate)
    if message_type is None:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            f"unsupported state-advancing write kind: {candidate!r}",
        )
    return message_type, message_type


def _validate_inputs(
    current_identity: Optional[Mapping[str, Any]],
    expected_source_digest: Optional[str],
    actor_cursor: Optional[int],
) -> tuple[Mapping[str, Any], str, int, str]:
    if not isinstance(current_identity, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "current execution identity must be an object")

    missing = [field for field in _REQUIRED_CURRENT_FIELDS if field not in current_identity]
    if "contract_digest" not in current_identity and "parent_contract_digest" not in current_identity:
        missing.append("contract_digest")
    if missing:
        _fail(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "current execution identity is missing: " + ", ".join(missing),
        )

    if not isinstance(expected_source_digest, str) or not expected_source_digest:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "expected_source_digest must be a non-empty string")

    if isinstance(actor_cursor, bool) or not isinstance(actor_cursor, int) or actor_cursor < -1:
        _fail(
            MailboxV2ErrorCode.INVALID_SEQUENCE,
            "actor_cursor must be an integer greater than or equal to -1",
        )

    contract_digest = current_identity.get("contract_digest", current_identity.get("parent_contract_digest"))
    if not isinstance(contract_digest, str) or not contract_digest:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "current contract_digest must be a non-empty string")
    return current_identity, expected_source_digest, actor_cursor, contract_digest


def validate_state_advancing_write(
    envelope: EnvelopeInput,
    current_identity: Optional[Mapping[str, Any]] = None,
    expected_source_digest: Optional[str] = None,
    actor_cursor: Optional[int] = None,
    write_kind: StateAdvancingWriteKind | str | None = None,
) -> StateAdvancingWriteDecision:
    """Evaluate whether a child, Mixer, or parent terminal write is current.

    The exact predicate is the architecture §22.2 contract:

    * run_id, node_id, plan_version and attempt_id match current state;
    * lease_generation matches current state;
    * the envelope contract digest matches the current parent contract digest;
    * the envelope source digest matches the expected source digest; and
    * the producer sequence is newer than its durable actor cursor.

    A failed predicate returns ``STALE_RESULT`` with ``evidence_only=True`` and
    ``advances_state=False``.  It never mutates ``current_identity`` or any
    caller-owned object.  Malformed inputs and write-kind/message-type pairs
    fail closed with a protocol validation error instead of being classified as
    stale evidence.
    """

    expected_message_type, canonical_kind = _canonical_write_kind(write_kind)
    validated = _coerce_envelope(envelope)
    if validated.to_dict()["message_type"] != expected_message_type:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            f"write kind {canonical_kind!r} requires message_type {expected_message_type!r}",
        )

    current, expected_source, cursor, current_contract_digest = _validate_inputs(
        current_identity,
        expected_source_digest,
        actor_cursor,
    )
    actual = validated.execution_identity
    failed: list[str] = []

    for field in _REQUIRED_CURRENT_FIELDS:
        if actual[field] != current[field]:
            failed.append(field)
    if actual["contract_digest"] != current_contract_digest:
        failed.append("contract_digest")
    if actual["source_digest"] != expected_source:
        failed.append("source_digest")
    if validated.seq <= cursor:
        failed.append("seq")

    if failed:
        return StateAdvancingWriteDecision(
            write_kind=canonical_kind,
            disposition=StateAdvancingDisposition.STALE_RESULT.value,
            advances_state=False,
            evidence_only=True,
            envelope_digest=validated.digest(),
            failed_checks=tuple(failed),
        )

    return StateAdvancingWriteDecision(
        write_kind=canonical_kind,
        disposition=StateAdvancingDisposition.ACCEPTED.value,
        advances_state=True,
        evidence_only=False,
        envelope_digest=validated.digest(),
    )


# Descriptive alias for callers that use the architecture's "evaluate" wording.
evaluate_state_advancing_write = validate_state_advancing_write


__all__ = [
    "StateAdvancingDisposition",
    "StateAdvancingWriteDecision",
    "StateAdvancingWriteKind",
    "evaluate_state_advancing_write",
    "validate_state_advancing_write",
]
