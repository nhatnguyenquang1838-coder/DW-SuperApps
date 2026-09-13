"""Pure Controller-side retry binding for one mailbox/v2 request.

A retry is a new execution attempt for the same logical ``TaskContract``.  The
Controller supplies every new identity value; this module only validates the
monotonic/uniqueness boundary and copies the prior request's contract.  It does
not generate IDs, persist state, write a mailbox, emit a wake-up, or dispatch an
Executor.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Mapping

from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            f"{field} must be a non-empty string",
        )
    return value


def _new_text(value: Any, field: str, previous: str) -> str:
    candidate = _text(value, field)
    if candidate == previous:
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            f"{field} must be new for a retry attempt",
        )
    return candidate


def retry_bounded_mailbox_request(
    previous: BoundedMailboxRequest | Mapping[str, Any],
    *,
    message_id: str,
    seq: int,
    attempt_id: str,
    lease_generation: int,
    fencing_token: str,
    lease_expires_at: str,
    idempotency_key: str,
    correlation_id: str | None = None,
) -> BoundedMailboxRequest:
    """Create a Controller-bound request for the next attempt.

    The prior request is compiled first so malformed or unsupported input cannot
    become a retry.  Only attempt/event identity changes: the logical contract,
    scope, source/standards bindings, authority constraints, recipient and
    execution payload are copied unchanged.  ``idempotency_key`` is the
    normative mailbox/v2 per-attempt idempotency scope.
    """

    if isinstance(previous, Mapping):
        previous = BoundedMailboxRequest.from_mapping(previous)
    if not isinstance(previous, BoundedMailboxRequest):
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "previous retry input must be BoundedMailboxRequest or object",
        )

    # Validate the complete prior contract before deriving a new attempt.  The
    # compiled envelope is intentionally not returned: this function returns a
    # caller binding, leaving compilation/persistence to the existing boundary.
    compile_bounded_mailbox_request(previous)

    new_message_id = _new_text(message_id, "message_id", previous.message_id)
    new_attempt_id = _new_text(attempt_id, "attempt_id", previous.attempt_id)
    new_fencing_token = _new_text(fencing_token, "fencing_token", previous.fencing_token)
    new_idempotency_key = _new_text(
        idempotency_key,
        "idempotency_key",
        previous.idempotency_key,
    )
    new_expiry = _text(lease_expires_at, "lease_expires_at")

    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "seq must be an integer greater than or equal to zero",
        )
    if seq <= previous.seq:
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.INVALID_SEQUENCE,
            "retry mailbox sequence must be newer than the previous request",
        )

    if (
        isinstance(lease_generation, bool)
        or not isinstance(lease_generation, int)
        or lease_generation < 0
    ):
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "lease_generation must be an integer greater than or equal to zero",
        )
    if lease_generation <= previous.lease_generation:
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.STALE_GENERATION,
            "retry lease_generation must be newer than the previous attempt",
        )

    new_correlation_id = previous.correlation_id if correlation_id is None else _text(
        correlation_id,
        "correlation_id",
    )

    # Deep-copy the immutable-in-use input before replacing identity fields so
    # mutable mapping/sequence members cannot alias the prior binding.
    candidate = copy.deepcopy(previous)
    return replace(
        candidate,
        message_id=new_message_id,
        seq=seq,
        correlation_id=new_correlation_id,
        attempt_id=new_attempt_id,
        attempt_number=previous.attempt_number + 1,
        lease_generation=lease_generation,
        fencing_token=new_fencing_token,
        lease_expires_at=new_expiry,
        idempotency_key=new_idempotency_key,
    )


# Descriptive alias for Controller call sites; there is one implementation and
# no second retry protocol surface.
create_retry_attempt = retry_bounded_mailbox_request


__all__ = [
    "create_retry_attempt",
    "retry_bounded_mailbox_request",
]
