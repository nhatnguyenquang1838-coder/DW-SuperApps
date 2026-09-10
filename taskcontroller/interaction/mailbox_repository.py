"""Additive WP2 mailbox repository primitives for mailbox/v2.

The in-memory implementation is a deterministic test/reference adapter.  It
models the append-only and exact-readback contracts without making GitHub,
Slack, ledger or Hermes calls.  A remote adapter can implement the same
``MailboxRepository`` protocol in a later bounded slice.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple, Union, runtime_checkable

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    V2_PROTOCOL,
    canonical_digest,
)


EnvelopeInput = Union[V2MailboxEnvelope, Mapping[str, Any]]


@dataclass(frozen=True)
class MailboxEvent:
    """One immutable append-only event and its canonical envelope binding."""

    mailbox_ref: str
    event_id: str
    event_seq: int
    producer_namespace: str
    logical_seq: int
    previous_event_digest: Optional[str]
    envelope_digest: str
    idempotency_key: str
    envelope: V2MailboxEnvelope
    event_digest: str

    def __post_init__(self) -> None:
        expected = canonical_digest(self._body())
        if self.event_digest != expected:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                f"event digest mismatch: expected {expected}",
            )

    def _body(self) -> Dict[str, Any]:
        return {
            "mailbox_ref": self.mailbox_ref,
            "event_id": self.event_id,
            "event_seq": self.event_seq,
            "producer_namespace": self.producer_namespace,
            "logical_seq": self.logical_seq,
            "previous_event_digest": self.previous_event_digest,
            "envelope_digest": self.envelope_digest,
            "idempotency_key": self.idempotency_key,
            "envelope": self.envelope.to_dict(),
        }

    def to_dict(self) -> Dict[str, Any]:
        value = self._body()
        value["digest"] = self.event_digest
        return value


CURSOR_PROTOCOL = "dw.taskcontroller.mailbox-cursor/v1"


@dataclass(frozen=True)
class MailboxActorCursor:
    """Serializable durable cursor for one mailbox actor/run/node binding."""

    mailbox_ref: str
    run_id: str
    node_id: str
    actor_namespace: str
    last_logical_seq: int = -1
    last_event_seq: int = -1
    last_event_id: Optional[str] = None
    last_event_digest: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("mailbox_ref", "run_id", "node_id", "actor_namespace"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.SCHEMA_INVALID,
                    f"cursor {name} must be a non-empty string",
                )
        for name in ("last_logical_seq", "last_event_seq"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < -1:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    f"cursor {name} must be an integer greater than or equal to -1",
                )
        if (self.last_event_id is None) != (self.last_event_digest is None):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "cursor event ID and digest must be supplied together",
            )
        if self.last_event_seq == -1 and (
            self.last_logical_seq != -1 or self.last_event_id is not None
        ):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "an initial cursor cannot contain an acknowledged event",
            )
        if self.last_event_seq >= 0 and (
            self.last_logical_seq < 0
            or self.last_event_id is None
            or self.last_event_digest is None
        ):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "an acknowledged cursor requires event identity and logical sequence",
            )
        for name in ("last_event_id", "last_event_digest"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.SCHEMA_INVALID,
                    f"cursor {name} must be non-empty when supplied",
                )

    @classmethod
    def initial(
        cls,
        mailbox_ref: str,
        *,
        run_id: str,
        node_id: str,
        actor_namespace: str,
    ) -> "MailboxActorCursor":
        """Create the deterministic cursor before an actor consumes any event."""

        return cls(
            mailbox_ref=mailbox_ref,
            run_id=run_id,
            node_id=node_id,
            actor_namespace=actor_namespace,
        )

    def _validate_event_binding(self, event: "MailboxEvent") -> None:
        if not isinstance(event, MailboxEvent):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "cursor observation requires a MailboxEvent",
            )
        if event.mailbox_ref != self.mailbox_ref:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "event mailbox does not match cursor mailbox",
            )
        if (
            event.envelope.run_id != self.run_id
            or event.envelope.node_id != self.node_id
            or event.producer_namespace != self.actor_namespace
        ):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "event identity does not match cursor actor binding",
            )

    def observe(self, event: "MailboxEvent") -> "MailboxActorCursor":
        """Advance only over a newer event, treating the exact event as a no-op."""

        self._validate_event_binding(event)
        exact_duplicate = (
            event.event_seq == self.last_event_seq
            and event.logical_seq == self.last_logical_seq
            and event.event_id == self.last_event_id
            and event.event_digest == self.last_event_digest
        )
        if exact_duplicate:
            return self
        if event.event_seq <= self.last_event_seq or event.logical_seq <= self.last_logical_seq:
            if event.event_seq == self.last_event_seq or event.logical_seq == self.last_logical_seq:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "cursor position is bound to a different event",
                )
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.INVALID_SEQUENCE,
                "event is not newer than the durable actor cursor",
            )
        return replace(
            self,
            last_logical_seq=event.logical_seq,
            last_event_seq=event.event_seq,
            last_event_id=event.event_id,
            last_event_digest=event.event_digest,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a deterministic, restart-safe cursor representation."""

        return {
            "protocol": CURSOR_PROTOCOL,
            "mailbox_ref": self.mailbox_ref,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "actor_namespace": self.actor_namespace,
            "last_logical_seq": self.last_logical_seq,
            "last_event_seq": self.last_event_seq,
            "last_event_id": self.last_event_id,
            "last_event_digest": self.last_event_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MailboxActorCursor":
        """Reconstruct a cursor without accepting unknown or inferred fields."""

        if not isinstance(payload, Mapping):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "cursor payload must be an object",
            )
        if payload.get("protocol") != CURSOR_PROTOCOL:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL,
                f"expected {CURSOR_PROTOCOL}",
            )
        allowed = {
            "protocol",
            "mailbox_ref",
            "run_id",
            "node_id",
            "actor_namespace",
            "last_logical_seq",
            "last_event_seq",
            "last_event_id",
            "last_event_digest",
        }
        unexpected = set(payload) - allowed
        if unexpected:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "cursor contains unknown fields: " + ", ".join(sorted(unexpected)),
            )
        try:
            return cls(
                mailbox_ref=payload["mailbox_ref"],
                run_id=payload["run_id"],
                node_id=payload["node_id"],
                actor_namespace=payload["actor_namespace"],
                last_logical_seq=payload.get("last_logical_seq", -1),
                last_event_seq=payload.get("last_event_seq", -1),
                last_event_id=payload.get("last_event_id"),
                last_event_digest=payload.get("last_event_digest"),
            )
        except KeyError as exc:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "cursor payload is missing a required field",
            ) from exc


@dataclass(frozen=True)
class WriteReceipt:
    """Exact identity returned for a newly appended or idempotent write."""

    mailbox_ref: str
    event_id: str
    event_seq: int
    message_id: str
    envelope_digest: str
    event_digest: str
    idempotent: bool = False


@dataclass(frozen=True)
class QuarantineReceipt:
    """Auditable rejection record for an invalid raw mailbox payload."""

    mailbox_ref: str
    error_code: str
    message: str
    raw_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_payload", copy.deepcopy(dict(self.raw_payload)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mailbox_ref": self.mailbox_ref,
            "error_code": self.error_code,
            "message": self.message,
            "raw_payload": copy.deepcopy(dict(self.raw_payload)),
        }


@dataclass(frozen=True)
class MailboxSnapshot:
    """Deterministic read model derived from the accepted append-only log."""

    mailbox_ref: str
    events: Tuple[MailboxEvent, ...]
    last_event_seq: int
    accepted_state: Mapping[str, Any]
    producer_cursors: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "accepted_state", copy.deepcopy(dict(self.accepted_state)))
        object.__setattr__(self, "producer_cursors", dict(self.producer_cursors))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mailbox_ref": self.mailbox_ref,
            "last_event_seq": self.last_event_seq,
            "events": [event.to_dict() for event in self.events],
            "accepted_state": copy.deepcopy(dict(self.accepted_state)),
            "producer_cursors": dict(self.producer_cursors),
        }


@runtime_checkable
class MailboxRepository(Protocol):
    """Kernel-facing persistence boundary; no raw GitHub comment dependency."""

    def capabilities(self) -> Mapping[str, Any]:
        ...

    def read(self, mailbox_ref: str) -> MailboxSnapshot:
        ...

    def write(
        self,
        mailbox_ref: str,
        expected_seq: int,
        envelope: EnvelopeInput,
        *,
        expected_identity: Optional[Mapping[str, Any]] = None,
    ) -> WriteReceipt:
        ...

    def exact_readback(self, receipt: WriteReceipt) -> MailboxSnapshot:
        ...

    def scan_after(self, mailbox_ref: str, cursor: int) -> Tuple[MailboxEvent, ...]:
        ...

    def read_cursor(
        self,
        mailbox_ref: str,
        run_id: str,
        node_id: str,
        actor_namespace: str,
    ) -> MailboxActorCursor:
        ...

    def scan_after_cursor(self, cursor: MailboxActorCursor) -> Tuple[MailboxEvent, ...]:
        ...

    def acknowledge_cursor(self, cursor: MailboxActorCursor) -> MailboxActorCursor:
        ...


class InMemoryMailboxRepository:
    """Thread-safe reference repository for append-only mailbox/v2 tests."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mailboxes: Dict[str, List[MailboxEvent]] = {}
        self._idempotency: Dict[Tuple[str, str], WriteReceipt] = {}
        self._quarantine: Dict[str, List[QuarantineReceipt]] = {}
        self._actor_cursors: Dict[Tuple[str, str, str, str], MailboxActorCursor] = {}

    def capabilities(self) -> Dict[str, Any]:
        return {
            "protocol": V2_PROTOCOL,
            "adapter": "in_memory",
            "append_only": True,
            "supports_v1": False,
            "supports_v2": True,
            "operations": [
                "read",
                "write",
                "exact_readback",
                "scan_after",
                "read_cursor",
                "scan_after_cursor",
                "acknowledge_cursor",
            ],
        }

    @staticmethod
    def _validate_ref(mailbox_ref: str) -> None:
        if not isinstance(mailbox_ref, str) or not mailbox_ref:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "mailbox_ref must be a non-empty string",
            )

    @staticmethod
    def _validate_expected_seq(expected_seq: int) -> None:
        if isinstance(expected_seq, bool) or not isinstance(expected_seq, int) or expected_seq < -1:
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.INVALID_SEQUENCE,
                "expected_seq must be an integer greater than or equal to -1",
            )

    @staticmethod
    def _coerce_envelope(envelope: EnvelopeInput) -> V2MailboxEnvelope:
        if isinstance(envelope, V2MailboxEnvelope):
            return envelope
        if isinstance(envelope, Mapping):
            return V2MailboxEnvelope.from_dict(envelope)
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "repository write requires a v2 envelope or mapping",
        )

    @staticmethod
    def _receipt(event: MailboxEvent, *, idempotent: bool = False) -> WriteReceipt:
        return WriteReceipt(
            mailbox_ref=event.mailbox_ref,
            event_id=event.event_id,
            event_seq=event.event_seq,
            message_id=event.envelope.to_dict()["message_id"],
            envelope_digest=event.envelope_digest,
            event_digest=event.event_digest,
            idempotent=idempotent,
        )

    def _build_snapshot(self, mailbox_ref: str) -> MailboxSnapshot:
        events = tuple(self._mailboxes.get(mailbox_ref, ()))
        producer_cursors: Dict[str, int] = {}
        for event in events:
            producer_cursors[event.producer_namespace] = max(
                producer_cursors.get(event.producer_namespace, -1),
                event.logical_seq,
            )
        producer_cursors = dict(sorted(producer_cursors.items()))
        accepted_state = {
            "accepted_event_ids": [event.event_id for event in events],
            "last_event_digest": events[-1].event_digest if events else None,
            "last_event_seq": len(events) - 1,
            "producer_sequences": producer_cursors,
        }
        return MailboxSnapshot(
            mailbox_ref=mailbox_ref,
            events=events,
            last_event_seq=len(events) - 1,
            accepted_state=accepted_state,
            producer_cursors=producer_cursors,
        )

    def read(self, mailbox_ref: str) -> MailboxSnapshot:
        self._validate_ref(mailbox_ref)
        with self._lock:
            return self._build_snapshot(mailbox_ref)

    def write(
        self,
        mailbox_ref: str,
        expected_seq: int,
        envelope: EnvelopeInput,
        *,
        expected_identity: Optional[Mapping[str, Any]] = None,
    ) -> WriteReceipt:
        self._validate_ref(mailbox_ref)
        self._validate_expected_seq(expected_seq)
        try:
            validated = self._coerce_envelope(envelope)
        except TaskControllerValidationError as exc:
            if isinstance(envelope, Mapping):
                self._record_quarantine(mailbox_ref, envelope, exc)
            raise
        if expected_identity is not None:
            validated.validate_current_identity(expected_identity)
        with self._lock:
            key = (mailbox_ref, validated.idempotency_key)
            existing_receipt = self._idempotency.get(key)
            if existing_receipt is not None:
                if existing_receipt.envelope_digest == validated.digest():
                    return replace(existing_receipt, idempotent=True)
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "idempotency key was reused with a different envelope digest",
                )

            events = self._mailboxes.setdefault(mailbox_ref, [])
            current_seq = len(events) - 1
            if expected_seq != current_seq:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    f"expected mailbox sequence {expected_seq}, current sequence is {current_seq}",
                )
            producer_last_seq = max(
                (
                    event.logical_seq
                    for event in events
                    if event.producer_namespace == validated.producer_namespace
                ),
                default=-1,
            )
            if validated.seq <= producer_last_seq:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    f"producer sequence {validated.seq} is not newer than {producer_last_seq}",
                )
            event_seq = len(events)
            event_body = {
                "mailbox_ref": mailbox_ref,
                "event_id": f"{mailbox_ref}:event-{event_seq}",
                "event_seq": event_seq,
                "producer_namespace": validated.producer_namespace,
                "logical_seq": validated.seq,
                "previous_event_digest": events[-1].event_digest if events else None,
                "envelope_digest": validated.digest(),
                "idempotency_key": validated.idempotency_key,
                "envelope": validated.to_dict(),
            }
            event = MailboxEvent(
                mailbox_ref=mailbox_ref,
                event_id=event_body["event_id"],
                event_seq=event_seq,
                producer_namespace=validated.producer_namespace,
                logical_seq=validated.seq,
                previous_event_digest=event_body["previous_event_digest"],
                envelope_digest=validated.digest(),
                idempotency_key=validated.idempotency_key,
                envelope=validated,
                event_digest=canonical_digest(event_body),
            )
            events.append(event)
            receipt = self._receipt(event)
            self._idempotency[key] = receipt
            return receipt

    def exact_readback(self, receipt: WriteReceipt) -> MailboxSnapshot:
        self._validate_ref(receipt.mailbox_ref)
        with self._lock:
            events = self._mailboxes.get(receipt.mailbox_ref, [])
            event = next((candidate for candidate in events if candidate.event_id == receipt.event_id), None)
            if event is None:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "receipt event is not present in the mailbox",
                )
            expected = self._receipt(event)
            if (
                receipt.event_seq != expected.event_seq
                or receipt.message_id != expected.message_id
                or receipt.envelope_digest != expected.envelope_digest
                or receipt.event_digest != expected.event_digest
            ):
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "exact readback receipt does not match persisted event",
                )
            return self._build_snapshot(receipt.mailbox_ref)

    def scan_after(self, mailbox_ref: str, cursor: int) -> Tuple[MailboxEvent, ...]:
        self._validate_ref(mailbox_ref)
        self._validate_expected_seq(cursor)
        with self._lock:
            return tuple(event for event in self._mailboxes.get(mailbox_ref, ()) if event.event_seq > cursor)

    @staticmethod
    def _cursor_key(cursor: MailboxActorCursor) -> Tuple[str, str, str, str]:
        return (
            cursor.mailbox_ref,
            cursor.run_id,
            cursor.node_id,
            cursor.actor_namespace,
        )

    def read_cursor(
        self,
        mailbox_ref: str,
        run_id: str,
        node_id: str,
        actor_namespace: str,
    ) -> MailboxActorCursor:
        """Read the durable cursor for one actor without advancing it."""

        self._validate_ref(mailbox_ref)
        initial = MailboxActorCursor.initial(
            mailbox_ref,
            run_id=run_id,
            node_id=node_id,
            actor_namespace=actor_namespace,
        )
        with self._lock:
            return self._actor_cursors.get(self._cursor_key(initial), initial)

    def scan_after_cursor(self, cursor: MailboxActorCursor) -> Tuple[MailboxEvent, ...]:
        """Return only bound-actor events newer than the durable cursor."""

        if not isinstance(cursor, MailboxActorCursor):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "scan_after_cursor requires a MailboxActorCursor",
            )
        key = self._cursor_key(cursor)
        with self._lock:
            durable = self._actor_cursors.get(key)
            if durable is not None:
                if (
                    cursor.last_event_seq < durable.last_event_seq
                    or cursor.last_logical_seq < durable.last_logical_seq
                ):
                    raise MailboxV2ValidationError(
                        MailboxV2ErrorCode.INVALID_SEQUENCE,
                        "scan cursor is behind the durable actor cursor",
                    )
                if cursor.last_event_seq == durable.last_event_seq and cursor != durable:
                    raise MailboxV2ValidationError(
                        MailboxV2ErrorCode.DIGEST_MISMATCH,
                        "scan cursor conflicts with the durable actor cursor",
                    )
            return tuple(
                event
                for event in self._mailboxes.get(cursor.mailbox_ref, ())
                if event.producer_namespace == cursor.actor_namespace
                and event.envelope.run_id == cursor.run_id
                and event.envelope.node_id == cursor.node_id
                and event.event_seq > cursor.last_event_seq
                and event.logical_seq > cursor.last_logical_seq
            )

    def acknowledge_cursor(self, cursor: MailboxActorCursor) -> MailboxActorCursor:
        """Persist a verified cursor monotonically and idempotently."""

        if not isinstance(cursor, MailboxActorCursor):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "acknowledge_cursor requires a MailboxActorCursor",
            )
        key = self._cursor_key(cursor)
        initial = MailboxActorCursor.initial(
            cursor.mailbox_ref,
            run_id=cursor.run_id,
            node_id=cursor.node_id,
            actor_namespace=cursor.actor_namespace,
        )
        with self._lock:
            current = self._actor_cursors.get(key, initial)
            if cursor == current:
                return current
            if (
                cursor.last_event_seq < current.last_event_seq
                or cursor.last_logical_seq < current.last_logical_seq
            ):
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    "acknowledged cursor cannot move backwards",
                )
            if (
                cursor.last_event_seq == current.last_event_seq
                or cursor.last_logical_seq == current.last_logical_seq
            ):
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "acknowledged cursor position conflicts with the durable cursor",
                )
            event = next(
                (
                    candidate
                    for candidate in self._mailboxes.get(cursor.mailbox_ref, ())
                    if candidate.event_id == cursor.last_event_id
                ),
                None,
            )
            if event is None:
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "acknowledged cursor event is not present in the mailbox",
                )
            cursor._validate_event_binding(event)
            if (
                event.event_seq != cursor.last_event_seq
                or event.logical_seq != cursor.last_logical_seq
                or event.event_digest != cursor.last_event_digest
            ):
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "acknowledged cursor does not match the mailbox event",
                )
            self._actor_cursors[key] = cursor
            return cursor

    def _record_quarantine(
        self,
        mailbox_ref: str,
        payload: Mapping[str, Any],
        error: TaskControllerValidationError,
    ) -> None:
        error_code = getattr(error, "code", MailboxV2ErrorCode.SCHEMA_INVALID)
        record = QuarantineReceipt(
            mailbox_ref=mailbox_ref,
            error_code=error_code,
            message=str(error),
            raw_payload=payload,
        )
        with self._lock:
            self._quarantine.setdefault(mailbox_ref, []).append(record)

    def quarantine_invalid(self, mailbox_ref: str, payload: Mapping[str, Any]) -> QuarantineReceipt:
        self._validate_ref(mailbox_ref)
        if not isinstance(payload, Mapping):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "quarantine payload must be an object",
            )
        try:
            self._coerce_envelope(payload)
        except TaskControllerValidationError as exc:
            self._record_quarantine(mailbox_ref, payload, exc)
            with self._lock:
                return self._quarantine[mailbox_ref][-1]
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "valid v2 envelopes cannot be quarantined",
        )

    def quarantined(self, mailbox_ref: str) -> Tuple[QuarantineReceipt, ...]:
        self._validate_ref(mailbox_ref)
        with self._lock:
            return tuple(self._quarantine.get(mailbox_ref, ()))


__all__ = [
    "CURSOR_PROTOCOL",
    "InMemoryMailboxRepository",
    "MailboxActorCursor",
    "MailboxEvent",
    "MailboxRepository",
    "MailboxSnapshot",
    "QuarantineReceipt",
    "WriteReceipt",
]
