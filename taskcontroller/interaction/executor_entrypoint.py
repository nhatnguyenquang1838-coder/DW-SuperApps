"""Mailbox-first Executor bootstrap for pointer-only wakeups.

The entrypoint is transport-neutral: a host supplies a mailbox reader, while the
canonical mailbox envelope supplies every executable field. A WakeupSignal is
only a pointer to that envelope; an optional human/Slack projection is accepted
for caller compatibility but is never inspected or copied into the request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope, A2A_PROTOCOL, EnvelopeKind
from taskcontroller.interaction.github_mailbox import parse_mailbox_comment
from taskcontroller.interaction.wakeup import WakeupSignal


EXECUTOR_MAILBOX_PROTOCOL = "dw.taskcontroller.executor-mailbox-entrypoint/v1"
EXECUTOR_MAILBOX_BOOTSTRAPPED = "BOOTSTRAPPED"
_EXECUTABLE_KINDS = frozenset({EnvelopeKind.COMMAND.value, EnvelopeKind.CORRECTION.value})
_DEFAULT_SUPPORTED_PROTOCOLS = frozenset({A2A_PROTOCOL})
_DEFAULT_ALLOWED_STATUSES = frozenset({"DISPATCHED"})
_ACTIVE_LEASE_STATUS = "ACTIVE"
_EXECUTOR_BINDING_KEY = "executor_binding"


@dataclass(frozen=True)
class ExecutorValidationPolicy:
    """Current Controller-issued identity required before Executor analysis.

    The policy is deliberately separate from ``A2AEnvelope`` and ``WakeupSignal``.
    In the v1 compatibility path, the canonical request carries the corresponding
    claims under the reserved ``state.executor_binding`` object; Slack projection
    never supplies or overrides any of them.
    """

    capability_id: str
    instance_id: str
    attempt_id: str
    lease_generation: int
    fencing_token: str
    supported_protocols: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_SUPPORTED_PROTOCOLS
    )
    allowed_statuses: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_ALLOWED_STATUSES
    )
    lease_status: str = _ACTIVE_LEASE_STATUS
    last_seen_seq: int = -1

    def __post_init__(self) -> None:
        for name in (
            "capability_id",
            "instance_id",
            "attempt_id",
            "fencing_token",
            "lease_status",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise TaskControllerValidationError(
                    f"executor validation policy {name} must be non-empty"
                )

        supported = frozenset(self.supported_protocols)
        if not supported or A2A_PROTOCOL not in supported:
            raise TaskControllerValidationError(
                "executor validation policy does not support the envelope schema"
            )
        if any(not isinstance(value, str) or not value.strip() for value in supported):
            raise TaskControllerValidationError(
                "executor validation policy supported schema values must be non-empty"
            )
        object.__setattr__(self, "supported_protocols", supported)

        statuses = frozenset(self.allowed_statuses)
        if not statuses or any(not isinstance(value, str) or not value.strip() for value in statuses):
            raise TaskControllerValidationError(
                "executor validation policy allowed statuses must be non-empty"
            )
        object.__setattr__(self, "allowed_statuses", statuses)

        if (
            not isinstance(self.lease_generation, int)
            or isinstance(self.lease_generation, bool)
            or self.lease_generation < 0
        ):
            raise TaskControllerValidationError(
                "executor validation policy lease_generation must be int >= 0"
            )
        if (
            not isinstance(self.last_seen_seq, int)
            or isinstance(self.last_seen_seq, bool)
            or self.last_seen_seq < -1
        ):
            raise TaskControllerValidationError(
                "executor validation policy last_seen_seq must be int >= -1"
            )


def _validate_executor_binding(
    envelope: A2AEnvelope,
    policy: ExecutorValidationPolicy,
) -> None:
    binding = envelope.state.get(_EXECUTOR_BINDING_KEY)
    if not isinstance(binding, Mapping):
        raise TaskControllerValidationError(
            "executor binding metadata is required before analysis"
        )

    protocol = binding.get("protocol")
    if protocol not in policy.supported_protocols or protocol != A2A_PROTOCOL:
        raise TaskControllerValidationError(
            "executor binding schema is unsupported"
        )

    expected_text = {
        "capability_id": policy.capability_id,
        "instance_id": policy.instance_id,
        "attempt_id": policy.attempt_id,
        "lease_status": policy.lease_status,
        "fencing_token": policy.fencing_token,
    }
    for field_name, expected in expected_text.items():
        if binding.get(field_name) != expected:
            raise TaskControllerValidationError(
                f"executor binding {field_name} does not match current policy"
            )

    if binding.get("status") not in policy.allowed_statuses:
        raise TaskControllerValidationError(
            "executor binding status is not executable"
        )

    generation = binding.get("lease_generation")
    if generation != policy.lease_generation:
        raise TaskControllerValidationError(
            "executor binding lease generation is stale"
        )


def _validate_signal_freshness(
    signal: WakeupSignal,
    policy: ExecutorValidationPolicy | None,
) -> None:
    if policy is not None and signal.seq <= policy.last_seen_seq:
        raise TaskControllerValidationError(
            "executor wakeup sequence is not newer than durable cursor"
        )


@runtime_checkable
class MailboxReader(Protocol):
    """Minimal host port required to exact-read one canonical mailbox record."""

    def read_mailbox(self, mailbox_ref: str) -> str:
        """Return the complete mailbox body for ``mailbox_ref``."""
        ...


@dataclass(frozen=True)
class ExecutorMailboxRequest:
    """Canonical request loaded from the mailbox named by one wakeup pointer."""

    signal: WakeupSignal
    envelope: A2AEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.signal, WakeupSignal):
            raise TaskControllerValidationError(
                "executor_mailbox_request requires WakeupSignal"
            )
        if not isinstance(self.envelope, A2AEnvelope):
            raise TaskControllerValidationError(
                "executor_mailbox_request requires A2AEnvelope"
            )
        if self.envelope.run_id != self.signal.run_id:
            raise TaskControllerValidationError(
                "executor mailbox run_id mismatch with wakeup pointer"
            )
        if self.envelope.sender != self.signal.sender:
            raise TaskControllerValidationError(
                "executor mailbox sender mismatch with wakeup pointer"
            )
        if self.envelope.recipient != self.signal.recipient:
            raise TaskControllerValidationError(
                "executor mailbox recipient mismatch with wakeup pointer"
            )
        if self.envelope.seq != self.signal.seq:
            raise TaskControllerValidationError(
                "executor mailbox sequence mismatch with wakeup pointer"
            )
        if self.envelope.kind not in _EXECUTABLE_KINDS:
            raise TaskControllerValidationError(
                "executor mailbox envelope is not executable COMMAND or CORRECTION"
            )
        if self.envelope.request is None or not self.envelope.request.strip():
            raise TaskControllerValidationError(
                "executor mailbox executable request must be non-empty"
            )

    @property
    def mailbox_ref(self) -> str:
        return self.signal.mailbox_ref

    @property
    def mailbox_seq(self) -> int:
        return self.signal.seq

    def to_dict(self) -> dict[str, Any]:
        """Return bounded bootstrap evidence without any Slack projection fields."""

        return {
            "protocol": EXECUTOR_MAILBOX_PROTOCOL,
            "status": EXECUTOR_MAILBOX_BOOTSTRAPPED,
            "run_id": self.signal.run_id,
            "sender": self.signal.sender,
            "recipient": self.signal.recipient,
            "mailbox_ref": self.mailbox_ref,
            "mailbox_seq": self.mailbox_seq,
            "envelope": self.envelope.to_dict(),
        }


class MailboxFirstExecutorEntrypoint:
    """Load one canonical Executor request from a pointer-only wakeup."""

    def __init__(
        self,
        mailbox_reader: MailboxReader,
        *,
        executor_actor: str,
        validation_policy: ExecutorValidationPolicy | None = None,
    ) -> None:
        if not isinstance(mailbox_reader, MailboxReader):
            raise TaskControllerValidationError(
                "mailbox-first entrypoint requires a MailboxReader"
            )
        if not isinstance(executor_actor, str) or not executor_actor.strip():
            raise TaskControllerValidationError(
                "mailbox-first entrypoint executor_actor must be non-empty"
            )
        if validation_policy is not None and not isinstance(
            validation_policy, ExecutorValidationPolicy
        ):
            raise TaskControllerValidationError(
                "mailbox-first entrypoint validation_policy is invalid"
            )
        self._mailbox_reader = mailbox_reader
        self._executor_actor = executor_actor
        self._validation_policy = validation_policy

    def bootstrap(
        self,
        signal: WakeupSignal,
        *,
        projection: object | None = None,
    ) -> ExecutorMailboxRequest:
        """Exact-read and validate the mailbox request named by ``signal``.

        ``projection`` is intentionally unused. It represents an optional Slack
        or human-plane rendering and has no authority over the canonical request.
        """

        if not isinstance(signal, WakeupSignal):
            raise TaskControllerValidationError(
                "mailbox-first bootstrap requires WakeupSignal"
            )
        _validate_signal_freshness(signal, self._validation_policy)
        if signal.recipient != self._executor_actor:
            raise TaskControllerValidationError(
                "executor mailbox recipient does not match entrypoint actor"
            )

        # Keep the compatibility argument visibly non-authoritative. Do not
        # validate, serialize, merge, or otherwise inspect it.
        del projection

        try:
            body = self._mailbox_reader.read_mailbox(signal.mailbox_ref)
        except Exception as exc:
            raise TaskControllerValidationError(
                "TASKCONTROLLER_EXECUTOR_MAILBOX_REJECTED: canonical mailbox read failed"
            ) from exc
        if not isinstance(body, str) or not body:
            raise TaskControllerValidationError(
                "TASKCONTROLLER_EXECUTOR_MAILBOX_REJECTED: canonical mailbox body is empty"
            )

        try:
            envelope = parse_mailbox_comment(body)
            request = ExecutorMailboxRequest(signal=signal, envelope=envelope)
            if self._validation_policy is not None:
                _validate_executor_binding(envelope, self._validation_policy)
            return request
        except TaskControllerValidationError as exc:
            raise TaskControllerValidationError(
                "TASKCONTROLLER_EXECUTOR_MAILBOX_REJECTED: canonical mailbox "
                f"does not match wakeup pointer ({exc})"
            ) from exc


__all__ = [
    "EXECUTOR_MAILBOX_BOOTSTRAPPED",
    "EXECUTOR_MAILBOX_PROTOCOL",
    "ExecutorMailboxRequest",
    "ExecutorValidationPolicy",
    "MailboxFirstExecutorEntrypoint",
    "MailboxReader",
]
