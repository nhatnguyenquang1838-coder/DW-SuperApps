"""Canonical high-integrity TaskController mailbox/v2 materialization.

This module is the single composition boundary for Controller machine writes once
mailbox/v2 is active.  Callers provide a bounded semantic request and durable
runtime dependencies; the runtime owns continuation persistence, envelope
compilation, mailbox event/CAS materialization, exact readback, dispatch ledger
commit, and durable producer cursor acknowledgement.

The materializer never grants execution authority.  It also rejects raw
transport-record fields and secret-bearing payload keys so an LLM/host cannot
hand-author GitHub mailbox records or accidentally persist credentials as
machine state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, NoReturn, Sequence

from taskcontroller.controlplane.continuation_dispatch import (
    prepare_v2_dispatch,
    recover_v2_dispatch,
)
from taskcontroller.controlplane.mailbox_dispatch import (
    MailboxDispatchOutcome,
    dispatch_v2_with_cursor,
)
from taskcontroller.controlplane.request_compiler import BoundedMailboxRequest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import (
    ContinuationStore,
    ControllerContinuation,
    recover_continuation,
)
from taskcontroller.interaction.mailbox_repository import MailboxRepository
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    V2_PROTOCOL,
)
from taskcontroller.runtime.dispatch_ledger import DispatchPrepared, DispatchProtocol


HIGH_INTEGRITY_RUNTIME_PROTOCOL = V2_PROTOCOL
LEGACY_V1_RUNTIME_SESSION = "taskcontroller/runtime/session.py"

_FORBIDDEN_TRANSPORT_KEYS = frozenset(
    {
        "protocol",
        "record_type",
        "mailbox_ref",
        "event_id",
        "event_seq",
        "previous_event_digest",
        "envelope_digest",
        "event_digest",
        "cursor",
        "record_seq",
        "previous_record_digest",
        "manifest_digest",
        "digest",
    }
)
_SECRET_KEY_FRAGMENTS = (
    "access_token",
    "api_key",
    "apikey",
    "approval_token",
    "authorization",
    "bearer",
    "credential",
    "password",
    "private_key",
    "secret",
)
_SAFE_SECRET_SUFFIXES = ("_ref", "_id", "_digest", "_hash", "_sha")


class HighIntegrityMaterializationError(TaskControllerValidationError):
    """Stable fail-closed materialization error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise HighIntegrityMaterializationError(code, message)


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _is_secret_key(key: str) -> bool:
    if key == "token_budget":
        return False
    if key.endswith(_SAFE_SECRET_SUFFIXES):
        return False
    return any(fragment in key for fragment in _SECRET_KEY_FRAGMENTS)


def _validate_semantic_payload(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _normalized_key(raw_key)
            child_path = f"{path}.{raw_key}"
            if key in _FORBIDDEN_TRANSPORT_KEYS:
                _fail(
                    "HAND_AUTHORED_TRANSPORT_FIELD_FORBIDDEN",
                    f"{child_path} is runtime-owned mailbox state",
                )
            if _is_secret_key(key):
                _fail(
                    "SECRET_BEARING_PAYLOAD_FORBIDDEN",
                    f"{child_path} must be represented by a reference/digest, never a raw secret",
                )
            _validate_semantic_payload(child, path=child_path)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _validate_semantic_payload(child, path=f"{path}[{index}]")


def validate_materialization_request(
    request: BoundedMailboxRequest | Mapping[str, Any],
) -> BoundedMailboxRequest:
    """Validate one semantic Controller request before any durable mutation."""

    if isinstance(request, BoundedMailboxRequest):
        bound = request
    elif isinstance(request, Mapping):
        try:
            bound = BoundedMailboxRequest.from_mapping(request)
        except MailboxV2ValidationError:
            raise
        except Exception as exc:  # defensive host boundary
            _fail("MATERIALIZATION_REQUEST_INVALID", str(exc))
    else:
        _fail(
            "MATERIALIZATION_REQUEST_INVALID",
            "request must be BoundedMailboxRequest or mapping",
        )
    _validate_semantic_payload(bound.payload)
    return bound


@dataclass(frozen=True, slots=True)
class ControllerMaterializationReceipt:
    """Exact-readback-backed receipt for one Controller mailbox/v2 transition."""

    envelope: V2MailboxEnvelope
    prepared: DispatchPrepared
    dispatch: MailboxDispatchOutcome
    continuation: ControllerContinuation
    authority_granted: bool = False

    def __post_init__(self) -> None:
        if self.envelope.protocol != V2_PROTOCOL:
            _fail("MATERIALIZATION_PROTOCOL_INVALID", "receipt requires mailbox/v2")
        if self.dispatch.committed.prepared_id != self.prepared.prepared_id:
            _fail(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "dispatch commit does not bind the prepared transition",
            )
        if self.dispatch.committed.envelope_digest != self.envelope.digest():
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "dispatch commit does not bind the compiled envelope",
            )
        if self.continuation.run_id != self.envelope.run_id:
            _fail(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "continuation does not bind the envelope run",
            )
        if self.authority_granted:
            _fail(
                "MATERIALIZER_AUTHORITY_GRANT_FORBIDDEN",
                "mailbox materialization must never grant execution authority",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": HIGH_INTEGRITY_RUNTIME_PROTOCOL,
            "authority_granted": False,
            "envelope_digest": self.envelope.digest(),
            "message_id": self.envelope.to_dict()["message_id"],
            "run_id": self.envelope.run_id,
            "node_id": self.envelope.node_id,
            "prepared": self.prepared.to_dict(),
            "dispatch": self.dispatch.to_dict(),
            "continuation": {
                "run_id": self.continuation.run_id,
                "controller_epoch": self.continuation.controller_epoch,
                "controller_mailbox_ref": self.continuation.controller_mailbox_ref,
                "controller_seq": self.continuation.controller_seq,
                "executor_mailbox_ref": self.continuation.executor_mailbox_ref,
                "expected_executor_seq": self.continuation.expected_executor_seq,
                "last_seen_executor_seq": self.continuation.last_seen_executor_seq,
                "phase": self.continuation.phase,
                "status": self.continuation.status,
                "next_action": self.continuation.next_action,
                "exact_head_sha": self.continuation.exact_head_sha,
                "updated_at": self.continuation.updated_at,
            },
        }


def materialize_controller_transition(
    *,
    continuation_store: ContinuationStore,
    repository: MailboxRepository,
    ledger: Any,
    checkpoint: ControllerContinuation,
    request: BoundedMailboxRequest | Mapping[str, Any],
    state_version: int,
    prepared_at: str,
    committed_at: str,
    actor: str = "controller",
) -> ControllerMaterializationReceipt:
    """Materialize exactly one canonical Controller mailbox/v2 transition.

    Ordering is fixed and runtime-owned:

    1. validate semantic request; reject transport/secret fields;
    2. persist + exact-read continuation and compile the deterministic v2 envelope;
    3. observe the current mailbox tail and prepare the exact successor;
    4. CAS append the canonical event + exact readback + DispatchCommitted;
    5. acknowledge/read back the durable producer cursor;
    6. recover/read back continuation and require the same checkpoint.

    Callers never supply record_type, event/cursor sequence, previous digests,
    event digests, or continuation record sequence.
    """

    if not isinstance(checkpoint, ControllerContinuation):
        _fail("MATERIALIZATION_CHECKPOINT_INVALID", "checkpoint is required")
    if not isinstance(repository, MailboxRepository):
        _fail("MATERIALIZATION_REPOSITORY_INVALID", "repository must implement MailboxRepository")
    if isinstance(state_version, bool) or not isinstance(state_version, int) or state_version < 0:
        _fail("MATERIALIZATION_STATE_VERSION_INVALID", "state_version must be int >= 0")
    if not isinstance(prepared_at, str) or not prepared_at:
        _fail("MATERIALIZATION_TIMESTAMP_INVALID", "prepared_at must be non-empty")
    if not isinstance(committed_at, str) or not committed_at:
        _fail("MATERIALIZATION_TIMESTAMP_INVALID", "committed_at must be non-empty")

    bound = validate_materialization_request(request)
    envelope = prepare_v2_dispatch(continuation_store, checkpoint, bound)

    snapshot = repository.read(checkpoint.controller_mailbox_ref)
    if snapshot.mailbox_ref != checkpoint.controller_mailbox_ref:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "repository snapshot does not bind the Controller mailbox",
        )

    matching = tuple(
        event
        for event in snapshot.events
        if event.idempotency_key == envelope.idempotency_key
    )
    if len(matching) > 1:
        _fail(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "multiple mailbox events reuse the materialization idempotency key",
        )
    if matching:
        existing = matching[0]
        if existing.envelope_digest != envelope.digest() or existing.envelope != envelope:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "idempotency key is already bound to different mailbox content",
            )
        expected_mailbox_seq = existing.event_seq - 1
    else:
        expected_mailbox_seq = snapshot.last_event_seq

    protocol = DispatchProtocol(repository=repository, ledger=ledger, actor=actor)
    prepared = protocol.prepare(
        envelope,
        mailbox_ref=checkpoint.controller_mailbox_ref,
        expected_mailbox_seq=expected_mailbox_seq,
        state_version=state_version,
        lease_generation=envelope.execution_identity["lease_generation"],
        prepared_at=prepared_at,
    )
    dispatch = dispatch_v2_with_cursor(
        protocol,
        prepared,
        envelope,
        committed_at=committed_at,
    )

    recovered = recover_v2_dispatch(continuation_store, envelope)
    durable = recover_continuation(continuation_store, checkpoint.run_id)
    if recovered != checkpoint or durable != checkpoint:
        _fail(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "continuation exact readback changed across mailbox materialization",
        )

    return ControllerMaterializationReceipt(
        envelope=envelope,
        prepared=prepared,
        dispatch=dispatch,
        continuation=durable,
        authority_granted=False,
    )


__all__ = [
    "ControllerMaterializationReceipt",
    "HIGH_INTEGRITY_RUNTIME_PROTOCOL",
    "HighIntegrityMaterializationError",
    "LEGACY_V1_RUNTIME_SESSION",
    "materialize_controller_transition",
    "validate_materialization_request",
]
