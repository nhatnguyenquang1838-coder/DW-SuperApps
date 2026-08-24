"""Executable TaskController A2A mailbox session boundary.

This is the canonical active machine-runtime path for TaskController. It binds
transport-neutral A2A envelopes, crash-safe continuation checkpoints, and a
host-provided mailbox backend. Slack is deliberately absent from machine
transport: hosts may emit pointer-only wakeups only after a successful mailbox
write/readback boundary.

Recovery is fail-closed except for two typed, monotonic crash windows created by
the required persist-before-dispatch ordering:

* an Executor observation was durably recorded but the Controller mailbox copy
  was not yet refreshed — recovery repairs that mailbox forward;
* a new Controller command checkpoint was durably recorded but the command never
  materialized in the Controller mailbox — recovery rolls the durable checkpoint
  back to the last materialized review/control boundary rather than fabricating
  a command that no Executor could have read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import (
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
    ContinuationStore,
    MailboxPollTarget,
    bind_continuation,
    continuation_from_envelope,
    persist_before_dispatch,
    persist_continuation,
    recover_continuation,
)
from taskcontroller.interaction.envelope import A2AEnvelope, EnvelopeKind
from taskcontroller.interaction.github_mailbox import (
    parse_mailbox_comment,
    render_mailbox_comment,
)

MAILBOX_BOOT_ERROR = "TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED"
POLL_OBSERVED = "OBSERVED"
POLL_STALE = "STALE"


class MailboxBackend(Protocol):
    """Host adapter for one-actor-one-mutable-mailbox semantics."""

    def ensure_mailbox(self, actor: str) -> str: ...

    def write_mailbox(self, mailbox_ref: str, body: str) -> None: ...

    def read_mailbox(self, mailbox_ref: str) -> str: ...


@dataclass(frozen=True)
class TaskControllerRuntimeSession:
    """Bound A2A state sufficient for dispatch, polling, and recovery."""

    controller_actor: str
    checkpoint: ControllerContinuation
    controller_envelope: A2AEnvelope

    @property
    def poll_target(self) -> MailboxPollTarget:
        return self.checkpoint.poll_target()


@dataclass(frozen=True)
class ExecutorMailboxObservation:
    """One exact Executor-mailbox observation."""

    status: str
    session: TaskControllerRuntimeSession
    envelope: A2AEnvelope | None = None

    def __post_init__(self) -> None:
        if self.status not in {POLL_OBSERVED, POLL_STALE}:
            raise TaskControllerValidationError(
                f"unsupported executor mailbox observation: {self.status!r}"
            )
        if self.status == POLL_OBSERVED and self.envelope is None:
            raise TaskControllerValidationError("OBSERVED mailbox result requires an envelope")
        if self.status == POLL_STALE and self.envelope is not None:
            raise TaskControllerValidationError("STALE mailbox result must not expose an envelope")


def _mailbox_boot_failure(
    detail: str, exc: Exception | None = None
) -> TaskControllerValidationError:
    error = TaskControllerValidationError(f"{MAILBOX_BOOT_ERROR}: {detail}")
    if exc is not None:
        error.__cause__ = exc
    return error


def _required_mailbox_ref(mailbox_backend: MailboxBackend, actor: str) -> str:
    try:
        mailbox_ref = mailbox_backend.ensure_mailbox(actor)
    except Exception as exc:
        raise _mailbox_boot_failure(f"cannot materialize mailbox for {actor}", exc) from exc
    if not isinstance(mailbox_ref, str) or not mailbox_ref.strip():
        raise _mailbox_boot_failure(f"mailbox ref missing for {actor}")
    return mailbox_ref


def _exact_write_readback(
    mailbox_backend: MailboxBackend,
    *,
    mailbox_ref: str,
    envelope: A2AEnvelope,
    checkpoint: ControllerContinuation,
) -> None:
    body = render_mailbox_comment(envelope)
    try:
        mailbox_backend.write_mailbox(mailbox_ref, body)
        readback = mailbox_backend.read_mailbox(mailbox_ref)
    except Exception as exc:
        raise _mailbox_boot_failure("controller mailbox write/readback failed", exc) from exc

    if readback != body:
        raise _mailbox_boot_failure("controller mailbox exact readback differs")
    try:
        parsed = parse_mailbox_comment(readback)
        embedded = continuation_from_envelope(parsed)
    except TaskControllerValidationError as exc:
        raise _mailbox_boot_failure("controller mailbox readback is invalid", exc) from exc
    if parsed != envelope or embedded != checkpoint:
        raise _mailbox_boot_failure("controller mailbox readback binding differs")


def _new_controller_envelope(
    *,
    checkpoint: ControllerContinuation,
    node_id: str,
    controller_actor: str,
    request: str,
    updated_at: str,
    kind: str,
) -> A2AEnvelope:
    envelope = A2AEnvelope(
        run_id=checkpoint.run_id,
        node_id=node_id,
        sender=controller_actor,
        recipient=checkpoint.executor_actor,
        seq=checkpoint.controller_seq,
        kind=kind,
        request=request,
        state={"head_sha": checkpoint.exact_head_sha},
        updated_at=updated_at,
    )
    return bind_continuation(envelope, checkpoint)


def _refresh_controller_checkpoint(
    mailbox_backend: MailboxBackend,
    *,
    session: TaskControllerRuntimeSession,
    checkpoint: ControllerContinuation,
) -> A2AEnvelope:
    """Rewrite the same Controller mailbox with a newer bounded checkpoint."""

    if checkpoint.controller_seq != session.controller_envelope.seq:
        raise TaskControllerValidationError(
            "checkpoint refresh cannot change Controller command sequence"
        )
    refreshed = bind_continuation(
        replace(session.controller_envelope, updated_at=checkpoint.updated_at),
        checkpoint,
    )
    _exact_write_readback(
        mailbox_backend,
        mailbox_ref=checkpoint.controller_mailbox_ref,
        envelope=refreshed,
        checkpoint=checkpoint,
    )
    return refreshed


def _same_recovery_identity(
    materialized: ControllerContinuation,
    durable: ControllerContinuation,
) -> bool:
    """Identity fields that may never be reconciled across a mismatch."""

    return (
        materialized.run_id == durable.run_id
        and materialized.controller_epoch == durable.controller_epoch
        and materialized.status == durable.status == ContinuationStatus.ACTIVE.value
        and materialized.controller_mailbox_ref == durable.controller_mailbox_ref
        and materialized.executor_actor == durable.executor_actor
        and materialized.executor_mailbox_ref == durable.executor_mailbox_ref
        and materialized.wakeup_binding == durable.wakeup_binding
        and materialized.exact_head_sha == durable.exact_head_sha
        and materialized.human_root_ref == durable.human_root_ref
    )


def _is_interrupted_observation_refresh(
    materialized: ControllerContinuation,
    durable: ControllerContinuation,
    envelope: A2AEnvelope,
) -> bool:
    """Durable REVIEW is exactly one observed Executor report ahead."""

    return (
        _same_recovery_identity(materialized, durable)
        and materialized.phase == ContinuationPhase.WAIT_EXECUTOR.value
        and materialized.next_action == "POLL_EXECUTOR"
        and durable.phase == ContinuationPhase.REVIEW_EXECUTOR.value
        and durable.next_action == "REVIEW_EXECUTOR"
        and materialized.controller_seq == durable.controller_seq == envelope.seq
        and durable.last_seen_executor_seq == materialized.last_seen_executor_seq + 1
        and durable.last_seen_executor_seq == materialized.expected_executor_seq
        and durable.expected_executor_seq == durable.last_seen_executor_seq + 1
    )


def _is_unmaterialized_dispatch(
    materialized: ControllerContinuation,
    durable: ControllerContinuation,
    envelope: A2AEnvelope,
) -> bool:
    """Persisted dispatch is one Controller seq ahead of the actual mailbox."""

    return (
        _same_recovery_identity(materialized, durable)
        and materialized.phase
        in {
            ContinuationPhase.REVIEW_EXECUTOR.value,
            ContinuationPhase.WAIT_CONTROLLER.value,
            ContinuationPhase.PRE_DISPATCH.value,
        }
        and durable.phase == ContinuationPhase.WAIT_EXECUTOR.value
        and durable.next_action == "POLL_EXECUTOR"
        and durable.controller_seq == materialized.controller_seq + 1
        and envelope.seq == materialized.controller_seq
        and durable.last_seen_executor_seq == materialized.last_seen_executor_seq
        and durable.expected_executor_seq == durable.last_seen_executor_seq + 1
    )


def boot_taskcontroller_session(
    *,
    continuation_store: ContinuationStore,
    mailbox_backend: MailboxBackend,
    run_id: str,
    node_id: str,
    controller_actor: str,
    executor_actor: str,
    exact_head_sha: str,
    wakeup_binding: str,
    request: str,
    updated_at: str,
    human_root_ref: str | None = None,
) -> TaskControllerRuntimeSession:
    """Materialize both mailboxes and exact-readback before first wake-up."""

    controller_mailbox_ref = _required_mailbox_ref(mailbox_backend, controller_actor)
    executor_mailbox_ref = _required_mailbox_ref(mailbox_backend, executor_actor)
    checkpoint = ControllerContinuation(
        run_id=run_id,
        controller_epoch=1,
        phase=ContinuationPhase.WAIT_EXECUTOR.value,
        status=ContinuationStatus.ACTIVE.value,
        next_action="POLL_EXECUTOR",
        controller_mailbox_ref=controller_mailbox_ref,
        controller_seq=1,
        executor_actor=executor_actor,
        executor_mailbox_ref=executor_mailbox_ref,
        expected_executor_seq=1,
        last_seen_executor_seq=0,
        wakeup_binding=wakeup_binding,
        exact_head_sha=exact_head_sha,
        human_root_ref=human_root_ref,
        updated_at=updated_at,
    )
    persist_before_dispatch(continuation_store, checkpoint)
    envelope = _new_controller_envelope(
        checkpoint=checkpoint,
        node_id=node_id,
        controller_actor=controller_actor,
        request=request,
        updated_at=updated_at,
        kind=EnvelopeKind.COMMAND.value,
    )
    _exact_write_readback(
        mailbox_backend,
        mailbox_ref=controller_mailbox_ref,
        envelope=envelope,
        checkpoint=checkpoint,
    )
    return TaskControllerRuntimeSession(
        controller_actor=controller_actor,
        checkpoint=checkpoint,
        controller_envelope=envelope,
    )


def dispatch_taskcontroller_command(
    continuation_store: ContinuationStore,
    mailbox_backend: MailboxBackend,
    session: TaskControllerRuntimeSession,
    *,
    request: str,
    updated_at: str,
    kind: str = EnvelopeKind.COMMAND.value,
) -> TaskControllerRuntimeSession:
    """Dispatch the next bounded command/correction through the same mailbox."""

    if not isinstance(session, TaskControllerRuntimeSession):
        raise TaskControllerValidationError("session must be TaskControllerRuntimeSession")
    if kind not in {EnvelopeKind.COMMAND.value, EnvelopeKind.CORRECTION.value}:
        raise TaskControllerValidationError("dispatch kind must be COMMAND or CORRECTION")
    current = session.checkpoint
    if current.status != ContinuationStatus.ACTIVE.value:
        raise TaskControllerValidationError("cannot dispatch from terminal TaskController session")
    if current.phase not in {
        ContinuationPhase.REVIEW_EXECUTOR.value,
        ContinuationPhase.WAIT_CONTROLLER.value,
        ContinuationPhase.PRE_DISPATCH.value,
    }:
        raise TaskControllerValidationError(
            "controller dispatch requires review/wait/pre-dispatch boundary"
        )

    checkpoint = replace(
        current,
        phase=ContinuationPhase.WAIT_EXECUTOR.value,
        next_action="POLL_EXECUTOR",
        controller_seq=current.controller_seq + 1,
        expected_executor_seq=current.last_seen_executor_seq + 1,
        updated_at=updated_at,
    )
    persist_before_dispatch(continuation_store, checkpoint)
    envelope = _new_controller_envelope(
        checkpoint=checkpoint,
        node_id=session.controller_envelope.node_id,
        controller_actor=session.controller_actor,
        request=request,
        updated_at=updated_at,
        kind=kind,
    )
    _exact_write_readback(
        mailbox_backend,
        mailbox_ref=checkpoint.controller_mailbox_ref,
        envelope=envelope,
        checkpoint=checkpoint,
    )
    return TaskControllerRuntimeSession(
        controller_actor=session.controller_actor,
        checkpoint=checkpoint,
        controller_envelope=envelope,
    )


def _poll_ref(checkpoint: ControllerContinuation) -> str:
    if checkpoint.status != ContinuationStatus.ACTIVE.value:
        raise TaskControllerValidationError("cannot poll terminal TaskController session")
    if checkpoint.phase == ContinuationPhase.WAIT_EXECUTOR.value:
        return checkpoint.poll_target().mailbox_ref
    if checkpoint.phase == ContinuationPhase.REVIEW_EXECUTOR.value:
        return checkpoint.executor_mailbox_ref
    raise TaskControllerValidationError("session is not at an executor mailbox boundary")


def poll_executor_mailbox(
    continuation_store: ContinuationStore,
    mailbox_backend: MailboxBackend,
    session: TaskControllerRuntimeSession,
) -> ExecutorMailboxObservation:
    """Read only the exact Executor mailbox and advance only exact expected seq."""

    if not isinstance(session, TaskControllerRuntimeSession):
        raise TaskControllerValidationError("session must be TaskControllerRuntimeSession")
    checkpoint = session.checkpoint
    mailbox_ref = _poll_ref(checkpoint)
    body = mailbox_backend.read_mailbox(mailbox_ref)
    try:
        envelope = parse_mailbox_comment(body)
    except TaskControllerValidationError as exc:
        raise TaskControllerValidationError("executor mailbox readback is invalid") from exc

    if envelope.run_id != checkpoint.run_id:
        raise TaskControllerValidationError("executor mailbox run_id mismatch")
    if envelope.sender != checkpoint.executor_actor:
        raise TaskControllerValidationError("executor mailbox actor mismatch")
    if envelope.recipient != session.controller_actor:
        raise TaskControllerValidationError("executor mailbox recipient mismatch")
    if envelope.state.get("head_sha") != checkpoint.exact_head_sha:
        raise TaskControllerValidationError("executor mailbox exact head mismatch")

    if envelope.seq <= checkpoint.last_seen_executor_seq:
        return ExecutorMailboxObservation(status=POLL_STALE, session=session)
    if checkpoint.phase != ContinuationPhase.WAIT_EXECUTOR.value:
        raise TaskControllerValidationError("executor mailbox advanced outside WAIT_EXECUTOR")
    if envelope.seq != checkpoint.expected_executor_seq:
        raise TaskControllerValidationError(
            "executor mailbox sequence gap: "
            f"expected {checkpoint.expected_executor_seq}, observed {envelope.seq}"
        )

    advanced = replace(
        checkpoint,
        phase=ContinuationPhase.REVIEW_EXECUTOR.value,
        next_action="REVIEW_EXECUTOR",
        last_seen_executor_seq=envelope.seq,
        expected_executor_seq=envelope.seq + 1,
        updated_at=envelope.updated_at,
    )
    persist_continuation(continuation_store, advanced)
    recovered = recover_continuation(continuation_store, advanced.run_id)
    if recovered != advanced:
        raise TaskControllerValidationError("executor observation continuation readback failed")

    refreshed_controller = _refresh_controller_checkpoint(
        mailbox_backend,
        session=session,
        checkpoint=advanced,
    )
    next_session = TaskControllerRuntimeSession(
        controller_actor=session.controller_actor,
        checkpoint=advanced,
        controller_envelope=refreshed_controller,
    )
    return ExecutorMailboxObservation(
        status=POLL_OBSERVED,
        session=next_session,
        envelope=envelope,
    )


def recover_taskcontroller_session(
    *,
    continuation_store: ContinuationStore,
    mailbox_backend: MailboxBackend,
    run_id: str,
    controller_actor: str,
) -> TaskControllerRuntimeSession:
    """Recover ACTIVE state and reconcile only known monotonic crash windows."""

    checkpoint = recover_continuation(continuation_store, run_id)
    if checkpoint is None:
        raise _mailbox_boot_failure("continuation checkpoint missing during recovery")
    if checkpoint.status != ContinuationStatus.ACTIVE.value:
        raise TaskControllerValidationError("cannot recover terminal TaskController session as active")

    body = mailbox_backend.read_mailbox(checkpoint.controller_mailbox_ref)
    try:
        envelope = parse_mailbox_comment(body)
        embedded = continuation_from_envelope(envelope)
    except TaskControllerValidationError as exc:
        raise _mailbox_boot_failure("controller mailbox recovery readback invalid", exc) from exc
    if embedded is None:
        raise _mailbox_boot_failure("controller mailbox continuation missing during recovery")
    if envelope.sender != controller_actor:
        raise _mailbox_boot_failure("controller mailbox actor mismatch during recovery")
    if envelope.recipient != checkpoint.executor_actor:
        raise _mailbox_boot_failure("controller mailbox executor mismatch during recovery")
    if envelope.state.get("head_sha") != checkpoint.exact_head_sha:
        raise _mailbox_boot_failure("controller mailbox exact head mismatch during recovery")

    if embedded == checkpoint:
        return TaskControllerRuntimeSession(
            controller_actor=controller_actor,
            checkpoint=checkpoint,
            controller_envelope=envelope,
        )

    if _is_interrupted_observation_refresh(embedded, checkpoint, envelope):
        stale_session = TaskControllerRuntimeSession(
            controller_actor=controller_actor,
            checkpoint=embedded,
            controller_envelope=envelope,
        )
        refreshed = _refresh_controller_checkpoint(
            mailbox_backend,
            session=stale_session,
            checkpoint=checkpoint,
        )
        return TaskControllerRuntimeSession(
            controller_actor=controller_actor,
            checkpoint=checkpoint,
            controller_envelope=refreshed,
        )

    if _is_unmaterialized_dispatch(embedded, checkpoint, envelope):
        # The newer command checkpoint was persisted, but the command body never
        # became the actor's mailbox record. No safe wake-up can have followed a
        # failed exact-readback boundary, so restore the last materialized
        # review/control boundary rather than inventing missing command content.
        persist_continuation(continuation_store, embedded)
        rolled_back = recover_continuation(continuation_store, run_id)
        if rolled_back != embedded:
            raise _mailbox_boot_failure(
                "unmaterialized dispatch rollback persistence/readback failed"
            )
        return TaskControllerRuntimeSession(
            controller_actor=controller_actor,
            checkpoint=embedded,
            controller_envelope=envelope,
        )

    raise _mailbox_boot_failure("controller mailbox continuation differs during recovery")


__all__ = [
    "A2AEnvelope",
    "ExecutorMailboxObservation",
    "MAILBOX_BOOT_ERROR",
    "MailboxBackend",
    "POLL_OBSERVED",
    "POLL_STALE",
    "TaskControllerRuntimeSession",
    "boot_taskcontroller_session",
    "dispatch_taskcontroller_command",
    "poll_executor_mailbox",
    "recover_taskcontroller_session",
]
