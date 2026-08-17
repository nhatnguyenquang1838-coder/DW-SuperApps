"""Crash-safe Controller continuation state for reference-based A2A.

The Controller's reasoning remains in the GPT host. This module persists only
bounded continuation metadata: enough to recover an ACTIVE run without replaying
chat or Slack history. The current GitHub pilot embeds the same checkpoint in the
Controller mailbox and may mirror it to the Run Ledger manifest table.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

from taskcontroller.audit.manifest import RunManifest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope

CONTINUATION_PROTOCOL = "dw.taskcontroller.continuation/v1"
CONTINUATION_MANIFEST_KIND = CONTINUATION_PROTOCOL
CONTINUATION_SCHEMA_VERSION = "1.0"
CONTINUATION_STATE_KEY = "controller_continuation"


class ContinuationPhase(str, Enum):
    PRE_DISPATCH = "PRE_DISPATCH"
    WAIT_EXECUTOR = "WAIT_EXECUTOR"
    REVIEW_EXECUTOR = "REVIEW_EXECUTOR"
    WAIT_CONTROLLER = "WAIT_CONTROLLER"
    TERMINAL = "TERMINAL"


class ContinuationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    TERMINAL = "TERMINAL"


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"controller_continuation.{name} must be non-empty")
    return value


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TaskControllerValidationError(f"controller_continuation.{name} must be int > 0")
    return value


@dataclass(frozen=True)
class MailboxPollTarget:
    """The complete bounded input for one silent polling read."""

    actor: str
    mailbox_ref: str
    last_seen_seq: int
    expected_seq: int

    def __post_init__(self) -> None:
        _required_text(self.actor, "poll_target.actor")
        _required_text(self.mailbox_ref, "poll_target.mailbox_ref")
        if not isinstance(self.last_seen_seq, int) or isinstance(self.last_seen_seq, bool) or self.last_seen_seq < 0:
            raise TaskControllerValidationError(
                "controller_continuation.poll_target.last_seen_seq must be int >= 0"
            )
        _positive_int(self.expected_seq, "poll_target.expected_seq")
        if self.expected_seq <= self.last_seen_seq:
            raise TaskControllerValidationError(
                "controller_continuation.poll_target.expected_seq must be newer than cursor"
            )


@dataclass(frozen=True)
class ControllerContinuation:
    run_id: str
    controller_epoch: int
    phase: str
    status: str
    next_action: str
    controller_mailbox_ref: str
    controller_seq: int
    executor_actor: str
    executor_mailbox_ref: str
    expected_executor_seq: int
    last_seen_executor_seq: int
    wakeup_binding: str
    exact_head_sha: str
    updated_at: str
    human_root_ref: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "next_action",
            "controller_mailbox_ref",
            "executor_actor",
            "executor_mailbox_ref",
            "wakeup_binding",
            "exact_head_sha",
            "updated_at",
        ):
            _required_text(getattr(self, name), name)
        _positive_int(self.controller_epoch, "controller_epoch")
        _positive_int(self.controller_seq, "controller_seq")
        _positive_int(self.expected_executor_seq, "expected_executor_seq")
        if (
            not isinstance(self.last_seen_executor_seq, int)
            or isinstance(self.last_seen_executor_seq, bool)
            or self.last_seen_executor_seq < 0
        ):
            raise TaskControllerValidationError(
                "controller_continuation.last_seen_executor_seq must be int >= 0"
            )
        if self.human_root_ref is not None:
            _required_text(self.human_root_ref, "human_root_ref")

        try:
            phase = ContinuationPhase(self.phase).value
            status = ContinuationStatus(self.status).value
        except (TypeError, ValueError) as exc:
            raise TaskControllerValidationError("controller_continuation phase/status unsupported") from exc
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "status", status)

        if status == ContinuationStatus.ACTIVE.value:
            if phase == ContinuationPhase.TERMINAL.value or self.next_action == "NONE":
                raise TaskControllerValidationError(
                    "ACTIVE controller continuation must retain a non-terminal next action"
                )
        elif phase != ContinuationPhase.TERMINAL.value or self.next_action != "NONE":
            raise TaskControllerValidationError(
                "TERMINAL controller continuation requires TERMINAL/NONE"
            )

        if phase == ContinuationPhase.WAIT_EXECUTOR.value:
            if self.expected_executor_seq <= self.last_seen_executor_seq:
                raise TaskControllerValidationError(
                    "WAIT_EXECUTOR expected_executor_seq must be newer than last_seen_executor_seq"
                )
            if self.next_action != "POLL_EXECUTOR":
                raise TaskControllerValidationError(
                    "WAIT_EXECUTOR controller continuation requires POLL_EXECUTOR"
                )

    def poll_target(self) -> MailboxPollTarget:
        if (
            self.status != ContinuationStatus.ACTIVE.value
            or self.phase != ContinuationPhase.WAIT_EXECUTOR.value
            or self.next_action != "POLL_EXECUTOR"
        ):
            raise TaskControllerValidationError(
                "controller continuation is not at an active executor-poll boundary"
            )
        return MailboxPollTarget(
            actor=self.executor_actor,
            mailbox_ref=self.executor_mailbox_ref,
            last_seen_seq=self.last_seen_executor_seq,
            expected_seq=self.expected_executor_seq,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol": CONTINUATION_PROTOCOL,
            "run_id": self.run_id,
            "controller_epoch": self.controller_epoch,
            "phase": self.phase,
            "status": self.status,
            "next_action": self.next_action,
            "controller_mailbox_ref": self.controller_mailbox_ref,
            "controller_seq": self.controller_seq,
            "executor_actor": self.executor_actor,
            "executor_mailbox_ref": self.executor_mailbox_ref,
            "expected_executor_seq": self.expected_executor_seq,
            "last_seen_executor_seq": self.last_seen_executor_seq,
            "wakeup_binding": self.wakeup_binding,
            "exact_head_sha": self.exact_head_sha,
            "updated_at": self.updated_at,
        }
        if self.human_root_ref is not None:
            payload["human_root_ref"] = self.human_root_ref
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ControllerContinuation":
        if not isinstance(payload, dict) or payload.get("protocol") != CONTINUATION_PROTOCOL:
            raise TaskControllerValidationError(
                f"controller_continuation.protocol must be {CONTINUATION_PROTOCOL!r}"
            )
        try:
            return cls(
                run_id=payload["run_id"],
                controller_epoch=payload["controller_epoch"],
                phase=payload["phase"],
                status=payload["status"],
                next_action=payload["next_action"],
                controller_mailbox_ref=payload["controller_mailbox_ref"],
                controller_seq=payload["controller_seq"],
                executor_actor=payload["executor_actor"],
                executor_mailbox_ref=payload["executor_mailbox_ref"],
                expected_executor_seq=payload["expected_executor_seq"],
                last_seen_executor_seq=payload["last_seen_executor_seq"],
                wakeup_binding=payload["wakeup_binding"],
                exact_head_sha=payload["exact_head_sha"],
                human_root_ref=payload.get("human_root_ref"),
                updated_at=payload["updated_at"],
            )
        except KeyError as exc:
            raise TaskControllerValidationError("malformed controller continuation") from exc

    def to_manifest(self, *, created_at: str | None = None) -> RunManifest:
        return RunManifest(
            run_id=self.run_id,
            manifest_kind=CONTINUATION_MANIFEST_KIND,
            schema_version=CONTINUATION_SCHEMA_VERSION,
            created_at=created_at or self.updated_at,
            updated_at=self.updated_at,
            metadata=self.to_dict(),
        )

    @classmethod
    def from_manifest(cls, manifest: RunManifest) -> "ControllerContinuation":
        if manifest.manifest_kind != CONTINUATION_MANIFEST_KIND:
            raise TaskControllerValidationError("unexpected continuation manifest kind")
        if manifest.schema_version != CONTINUATION_SCHEMA_VERSION:
            raise TaskControllerValidationError("unsupported continuation manifest version")
        checkpoint = cls.from_dict(manifest.metadata)
        if checkpoint.run_id != manifest.run_id:
            raise TaskControllerValidationError("continuation manifest run_id mismatch")
        return checkpoint


class ContinuationStore(Protocol):
    def save_manifest(self, manifest: RunManifest) -> None: ...
    def load_manifest(self, run_id: str, manifest_kind: str) -> RunManifest | None: ...


def persist_continuation(store: ContinuationStore, checkpoint: ControllerContinuation) -> None:
    existing = store.load_manifest(checkpoint.run_id, CONTINUATION_MANIFEST_KIND)
    created_at = existing.created_at if existing is not None else checkpoint.updated_at
    store.save_manifest(checkpoint.to_manifest(created_at=created_at))


def recover_continuation(
    store: ContinuationStore, run_id: str
) -> ControllerContinuation | None:
    manifest = store.load_manifest(run_id, CONTINUATION_MANIFEST_KIND)
    if manifest is None:
        return None
    return ControllerContinuation.from_manifest(manifest)


def persist_before_dispatch(
    store: ContinuationStore, checkpoint: ControllerContinuation
) -> ControllerContinuation:
    """Fail closed unless the WAIT_EXECUTOR checkpoint survives exact readback."""

    checkpoint.poll_target()
    persist_continuation(store, checkpoint)
    recovered = recover_continuation(store, checkpoint.run_id)
    if recovered != checkpoint:
        raise TaskControllerValidationError(
            "continuation checkpoint persistence/readback failed before dispatch"
        )
    return checkpoint


def assert_controller_may_finalize(checkpoint: ControllerContinuation) -> None:
    if checkpoint.status != ContinuationStatus.TERMINAL.value:
        raise TaskControllerValidationError(
            "ACTIVE TaskController run cannot emit semantic final/terminal response"
        )


def bind_continuation(
    envelope: A2AEnvelope, checkpoint: ControllerContinuation
) -> A2AEnvelope:
    """Embed the compact checkpoint into the durable Controller mailbox payload."""

    if envelope.run_id != checkpoint.run_id:
        raise TaskControllerValidationError("continuation/envelope run_id mismatch")
    if envelope.seq != checkpoint.controller_seq:
        raise TaskControllerValidationError("continuation/envelope controller seq mismatch")
    if envelope.recipient != checkpoint.executor_actor:
        raise TaskControllerValidationError("continuation/envelope executor mismatch")
    state = dict(envelope.state)
    state[CONTINUATION_STATE_KEY] = checkpoint.to_dict()
    return replace(envelope, state=state)


def continuation_from_envelope(envelope: A2AEnvelope) -> ControllerContinuation | None:
    payload = envelope.state.get(CONTINUATION_STATE_KEY)
    if payload is None:
        return None
    checkpoint = ControllerContinuation.from_dict(payload)
    if checkpoint.run_id != envelope.run_id or checkpoint.controller_seq != envelope.seq:
        raise TaskControllerValidationError("mailbox continuation does not bind its envelope")
    return checkpoint
