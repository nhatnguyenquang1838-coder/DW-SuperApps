"""Reference-based A2A envelope and mailbox cursor.

These types define TaskController interaction semantics without binding the core
to Slack, GitHub, HTTP A2A, IPC, NATS or Kafka/MSK transports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from taskcontroller.domain.values import InputRef
from taskcontroller.errors import TaskControllerValidationError

A2A_PROTOCOL = "dw.taskcontroller.a2a/v1"


class EnvelopeKind(str, Enum):
    COMMAND = "COMMAND"
    REPORT = "REPORT"
    REVIEW_REQUEST = "REVIEW_REQUEST"
    CORRECTION = "CORRECTION"
    TERMINAL = "TERMINAL"
    HEALTH = "HEALTH"


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"a2a_envelope.{name} must be non-empty")
    return value


@dataclass(frozen=True)
class A2AEnvelope:
    """Compact semantic message exchanged through a communication binding.

    Repository bodies and long chat history do not belong here. Inputs and
    artifacts are represented as durable references so each environment can
    resolve only the material it needs.
    """

    run_id: str
    node_id: str
    sender: str
    recipient: str
    seq: int
    kind: str
    inputs: tuple[InputRef, ...] | list[InputRef] = field(default_factory=tuple)
    artifact_refs: tuple[str, ...] | list[str] = field(default_factory=tuple)
    request: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    def __post_init__(self) -> None:
        for name in ("run_id", "node_id", "sender", "recipient", "updated_at"):
            _required_text(getattr(self, name), name)

        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq <= 0:
            raise TaskControllerValidationError("a2a_envelope.seq must be int > 0")

        try:
            kind = EnvelopeKind(self.kind).value
        except (TypeError, ValueError) as exc:
            raise TaskControllerValidationError(
                f"a2a_envelope.kind unsupported: {self.kind!r}"
            ) from exc
        object.__setattr__(self, "kind", kind)

        normalized_inputs = tuple(self.inputs)
        if any(not isinstance(item, InputRef) for item in normalized_inputs):
            raise TaskControllerValidationError("a2a_envelope.inputs must contain InputRef values")
        object.__setattr__(self, "inputs", normalized_inputs)

        normalized_artifacts = tuple(self.artifact_refs)
        if any(not isinstance(ref, str) or not ref for ref in normalized_artifacts):
            raise TaskControllerValidationError(
                "a2a_envelope.artifact_refs must contain non-empty strings"
            )
        object.__setattr__(self, "artifact_refs", normalized_artifacts)

        if self.request is not None and not isinstance(self.request, str):
            raise TaskControllerValidationError("a2a_envelope.request must be a string or null")
        if not isinstance(self.state, dict):
            raise TaskControllerValidationError("a2a_envelope.state must be an object")
        object.__setattr__(self, "state", dict(self.state))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol": A2A_PROTOCOL,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "seq": self.seq,
            "kind": self.kind,
            "inputs": [item.to_dict() for item in self.inputs],
            "artifact_refs": list(self.artifact_refs),
            "state": dict(self.state),
            "updated_at": self.updated_at,
        }
        if self.request is not None:
            payload["request"] = self.request
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "A2AEnvelope":
        if not isinstance(payload, dict):
            raise TaskControllerValidationError("a2a_envelope payload must be an object")
        if payload.get("protocol") != A2A_PROTOCOL:
            raise TaskControllerValidationError(
                f"a2a_envelope.protocol must be {A2A_PROTOCOL!r}"
            )
        try:
            inputs = tuple(InputRef.from_dict(item) for item in payload.get("inputs", []))
            return cls(
                run_id=payload["run_id"],
                node_id=payload["node_id"],
                sender=payload["sender"],
                recipient=payload["recipient"],
                seq=payload["seq"],
                kind=payload["kind"],
                inputs=inputs,
                artifact_refs=tuple(payload.get("artifact_refs", [])),
                request=payload.get("request"),
                state=payload.get("state", {}),
                updated_at=payload["updated_at"],
            )
        except (KeyError, TypeError) as exc:
            raise TaskControllerValidationError("malformed a2a_envelope payload") from exc


@dataclass(frozen=True)
class MailboxCursor:
    """Per-actor observation cursor sufficient for compact Controller recovery."""

    actor: str
    last_seen_seq: int = 0
    mailbox_ref: str | None = None
    last_head_sha: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.actor, "cursor.actor")
        if (
            not isinstance(self.last_seen_seq, int)
            or isinstance(self.last_seen_seq, bool)
            or self.last_seen_seq < 0
        ):
            raise TaskControllerValidationError("mailbox_cursor.last_seen_seq must be int >= 0")
        for name in ("mailbox_ref", "last_head_sha"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise TaskControllerValidationError(
                    f"mailbox_cursor.{name} must be non-empty when supplied"
                )

    def observe(self, envelope: A2AEnvelope) -> "MailboxCursor":
        if not isinstance(envelope, A2AEnvelope):
            raise TaskControllerValidationError("mailbox_cursor.observe requires A2AEnvelope")
        if envelope.sender != self.actor:
            raise TaskControllerValidationError(
                "mailbox_cursor actor does not match envelope sender"
            )
        if envelope.seq <= self.last_seen_seq:
            raise TaskControllerValidationError(
                "mailbox_cursor requires a strictly newer envelope sequence"
            )
        head_sha = self.last_head_sha
        candidate = envelope.state.get("head_sha")
        if candidate is not None:
            if not isinstance(candidate, str) or not candidate:
                raise TaskControllerValidationError("a2a_envelope.state.head_sha must be non-empty")
            head_sha = candidate
        return MailboxCursor(
            actor=self.actor,
            last_seen_seq=envelope.seq,
            mailbox_ref=self.mailbox_ref,
            last_head_sha=head_sha,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "actor": self.actor,
            "last_seen_seq": self.last_seen_seq,
        }
        if self.mailbox_ref is not None:
            payload["mailbox_ref"] = self.mailbox_ref
        if self.last_head_sha is not None:
            payload["last_head_sha"] = self.last_head_sha
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MailboxCursor":
        if not isinstance(payload, dict):
            raise TaskControllerValidationError("mailbox_cursor payload must be an object")
        try:
            return cls(
                actor=payload["actor"],
                last_seen_seq=payload.get("last_seen_seq", 0),
                mailbox_ref=payload.get("mailbox_ref"),
                last_head_sha=payload.get("last_head_sha"),
            )
        except KeyError as exc:
            raise TaskControllerValidationError("malformed mailbox_cursor payload") from exc
