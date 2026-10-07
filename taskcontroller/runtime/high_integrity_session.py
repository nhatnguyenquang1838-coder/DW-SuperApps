"""Canonical high-integrity TaskController mailbox/v2 runtime session.

This module is the single composition boundary for the canonical mailbox/v2
lifecycle: Controller materialization, Executor bootstrap, Controller
progress/result resume, and restart recovery. Callers provide bounded semantic
inputs and durable runtime dependencies; the runtime owns continuation
persistence, envelope compilation, mailbox event/CAS materialization, exact
readback, dispatch ledger commit, and durable producer cursor evidence.

The materializer never grants execution authority.  It also rejects raw
transport-record fields and secret-bearing payload keys so an LLM/host cannot
hand-author GitHub mailbox records or accidentally persist credentials as
machine state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
from taskcontroller.controlplane.result_resume import (
    ControllerResultPoll,
    POLL_NO_NEW_RESULT,
    POLL_PROGRESS_AVAILABLE,
    POLL_RESULT_AVAILABLE,
    poll_controller_terminal_result,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import (
    CONTINUATION_MANIFEST_KIND,
    ContinuationPhase,
    ContinuationStatus,
    ContinuationStore,
    ControllerContinuation,
    persist_continuation,
    recover_continuation,
)
from taskcontroller.interaction.executor_entrypoint import (
    MailboxV2ExecutorEntrypoint,
    V2ExecutorMailboxRequest,
    V2ExecutorValidationPolicy,
)
from taskcontroller.interaction.github_continuation_store import ContinuationWriteReceipt
from taskcontroller.interaction.github_mailbox_v2 import GitHubMailboxRecordReceipt
from taskcontroller.interaction.mailbox_repository import MailboxActorCursor, MailboxRepository
from taskcontroller.interaction.wakeup import WakeupSignal
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
    "token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "password",
    "private_key",
    "secret",
)
_SAFE_SECRET_KEYS = frozenset({"token_budget", "fencing_token"})
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
    if key in _SAFE_SECRET_KEYS:
        return False
    if key.endswith(_SAFE_SECRET_SUFFIXES):
        return False
    return any(fragment in key for fragment in _SECRET_KEY_FRAGMENTS)


def _validate_no_raw_secrets(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _normalized_key(raw_key)
            child_path = f"{path}.{raw_key}"
            if _is_secret_key(key):
                _fail(
                    "SECRET_BEARING_PAYLOAD_FORBIDDEN",
                    f"{child_path} must be represented by a reference/digest, never a raw secret",
                )
            _validate_no_raw_secrets(child, path=child_path)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _validate_no_raw_secrets(child, path=f"{path}[{index}]")


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
            _validate_no_raw_secrets({raw_key: child}, path=path)
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
    _validate_no_raw_secrets(
        {
            "scope": bound.scope,
            "source_refs": bound.source_refs,
            "standards_profile": bound.standards_profile,
            "evidence_refs": bound.evidence_refs,
            "environment_requirements": bound.environment_requirements,
            "authority_constraints": bound.authority_constraints,
            "execution_boundary": bound.execution_boundary,
        },
        path="request",
    )
    return bound


@dataclass(frozen=True, slots=True)
class ControllerMaterializationReceipt:
    """Exact-readback-backed receipt for one Controller mailbox/v2 transition."""

    envelope: V2MailboxEnvelope
    prepared: DispatchPrepared
    dispatch: MailboxDispatchOutcome
    continuation: ControllerContinuation
    event_remote: GitHubMailboxRecordReceipt
    cursor_remote: GitHubMailboxRecordReceipt
    continuation_remote: ContinuationWriteReceipt
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
            "remote_evidence": {
                "event": self.event_remote.to_dict(),
                "cursor": self.cursor_remote.to_dict(),
                "continuation": self.continuation_remote.to_dict(),
            },
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
    _validate_no_raw_secrets(envelope.to_dict(), path="envelope")

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

    event_receipt = getattr(repository, "event_receipt", None)
    cursor_receipt = getattr(repository, "cursor_receipt", None)
    continuation_receipt = getattr(continuation_store, "latest_receipt", None)
    if not callable(event_receipt) or not callable(cursor_receipt) or not callable(continuation_receipt):
        _fail(
            "REMOTE_RECEIPT_UNAVAILABLE",
            "canonical materialization requires immutable event/cursor/continuation remote receipts",
        )
    event_remote = event_receipt(
        checkpoint.controller_mailbox_ref,
        dispatch.committed.event_id,
    )
    cursor_remote = cursor_receipt(dispatch.cursor)
    continuation_remote = continuation_receipt(
        checkpoint.run_id,
        CONTINUATION_MANIFEST_KIND,
    )
    if not isinstance(event_remote, GitHubMailboxRecordReceipt):
        _fail("REMOTE_RECEIPT_INVALID", "event remote receipt is invalid")
    if not isinstance(cursor_remote, GitHubMailboxRecordReceipt):
        _fail("REMOTE_RECEIPT_INVALID", "cursor remote receipt is invalid")
    if not isinstance(continuation_remote, ContinuationWriteReceipt):
        _fail("REMOTE_RECEIPT_INVALID", "continuation remote receipt is invalid")

    return ControllerMaterializationReceipt(
        envelope=envelope,
        prepared=prepared,
        dispatch=dispatch,
        continuation=durable,
        event_remote=event_remote,
        cursor_remote=cursor_remote,
        continuation_remote=continuation_remote,
        authority_granted=False,
    )




@dataclass(frozen=True, slots=True)
class HighIntegrityResumeOutcome:
    """Controller continuation after consuming canonical Executor v2 output."""

    poll: ControllerResultPoll
    checkpoint: ControllerContinuation


@dataclass(frozen=True, slots=True)
class HighIntegrityRecovery:
    """Restart-safe current Controller state recovered without chat/Slack replay."""

    checkpoint: ControllerContinuation
    controller_envelope: V2MailboxEnvelope
    controller_cursor: MailboxActorCursor


def bootstrap_executor_v2(
    repository: MailboxRepository,
    signal: WakeupSignal,
    *,
    executor_actor: str,
    validation_policy: V2ExecutorValidationPolicy | None = None,
) -> V2ExecutorMailboxRequest:
    """Exact-read one canonical v2 Controller request and durably consume its cursor."""

    return MailboxV2ExecutorEntrypoint(
        repository,
        executor_actor=executor_actor,
        validation_policy=validation_policy,
    ).bootstrap(signal)


def resume_controller_v2(
    *,
    continuation_store: ContinuationStore,
    repository: MailboxRepository,
    checkpoint: ControllerContinuation,
    cursor: MailboxActorCursor,
    correlation_id: str,
    expected_identity: Mapping[str, Any],
    observed_at: str,
    expected_source_digest: str | None = None,
    expected_standards_digest: str | None = None,
    expected_result_digest: str | None = None,
    active_lease: Any = None,
    lease_now: str | None = None,
) -> HighIntegrityResumeOutcome:
    """Consume Executor progress/result and persist the next Controller continuation."""

    if checkpoint.status != ContinuationStatus.ACTIVE.value:
        _fail("RESUME_CHECKPOINT_INVALID", "cannot resume a terminal Controller checkpoint")
    if checkpoint.executor_mailbox_ref != cursor.mailbox_ref:
        _fail("RESUME_CURSOR_INVALID", "Executor result cursor mailbox differs from continuation")
    poll_kwargs: dict[str, Any] = {
        "correlation_id": correlation_id,
        "expected_identity": expected_identity,
        "expected_source_digest": expected_source_digest,
        "expected_standards_digest": expected_standards_digest,
        "expected_result_digest": expected_result_digest,
    }
    if active_lease is not None:
        poll_kwargs["active_lease"] = active_lease
        poll_kwargs["lease_now"] = lease_now
    poll = poll_controller_terminal_result(repository, cursor, **poll_kwargs)
    if poll.status == POLL_NO_NEW_RESULT:
        return HighIntegrityResumeOutcome(poll=poll, checkpoint=checkpoint)

    observed_seq = poll.cursor.last_logical_seq
    if observed_seq < checkpoint.last_seen_executor_seq:
        _fail("RESUME_SEQUENCE_INVALID", "Executor result cursor regressed continuation state")
    review_required = poll.status == POLL_RESULT_AVAILABLE
    if poll.status == POLL_PROGRESS_AVAILABLE and poll.progress_outcome is not None:
        review_required = (
            poll.progress_outcome.requires_controller_action
            or poll.progress_outcome.completed
        )
    next_checkpoint = replace(
        checkpoint,
        phase=(
            ContinuationPhase.REVIEW_EXECUTOR.value
            if review_required
            else ContinuationPhase.WAIT_EXECUTOR.value
        ),
        next_action="REVIEW_EXECUTOR" if review_required else "POLL_EXECUTOR",
        last_seen_executor_seq=observed_seq,
        expected_executor_seq=observed_seq + 1,
        updated_at=observed_at,
    )
    persist_continuation(continuation_store, next_checkpoint)
    durable = recover_continuation(continuation_store, next_checkpoint.run_id)
    if durable != next_checkpoint:
        _fail("RESUME_CONTINUATION_READBACK_FAILED", "resumed continuation exact readback differs")
    return HighIntegrityResumeOutcome(poll=poll, checkpoint=durable)


def recover_high_integrity_session(
    *,
    continuation_store: ContinuationStore,
    repository: MailboxRepository,
    run_id: str,
) -> HighIntegrityRecovery:
    """Recover current Controller state from continuation + mailbox/v2 only."""

    checkpoint = recover_continuation(continuation_store, run_id)
    if checkpoint is None:
        _fail("RECOVERY_CONTINUATION_MISSING", "durable Controller continuation is missing")
    snapshot = repository.read(checkpoint.controller_mailbox_ref)
    matches = tuple(
        event
        for event in snapshot.events
        if (
            event.envelope.run_id == checkpoint.run_id
            and event.logical_seq == checkpoint.controller_seq
            and event.envelope.to_dict().get("direction") == "controller_to_executor"
        )
    )
    if len(matches) != 1:
        _fail(
            "RECOVERY_CONTROLLER_EVENT_INVALID",
            "current Controller continuation does not resolve exactly one v2 request event",
        )
    event = matches[0]
    if checkpoint.phase == ContinuationPhase.WAIT_EXECUTOR.value:
        recovered = recover_v2_dispatch(continuation_store, event.envelope)
        if recovered != checkpoint:
            _fail("RECOVERY_CONTINUATION_MISMATCH", "request checkpoint differs from durable state")
    cursor = repository.read_cursor(
        checkpoint.controller_mailbox_ref,
        event.envelope.run_id,
        event.envelope.node_id,
        event.producer_namespace,
    )
    if cursor.last_event_seq < event.event_seq:
        _fail(
            "RECOVERY_CONTROLLER_CURSOR_STALE",
            "Controller producer cursor does not cover the current request event",
        )
    return HighIntegrityRecovery(
        checkpoint=checkpoint,
        controller_envelope=event.envelope,
        controller_cursor=cursor,
    )

__all__ = [
    "ControllerMaterializationReceipt",
    "HighIntegrityRecovery",
    "HighIntegrityResumeOutcome",
    "HIGH_INTEGRITY_RUNTIME_PROTOCOL",
    "HighIntegrityMaterializationError",
    "LEGACY_V1_RUNTIME_SESSION",
    "bootstrap_executor_v2",
    "materialize_controller_transition",
    "recover_high_integrity_session",
    "resume_controller_v2",
    "validate_materialization_request",
]
