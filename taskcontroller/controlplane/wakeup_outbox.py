"""TC-MBX-308 durable WakeupIntent outbox.

The outbox is deliberately transport-neutral.  It stores only the metadata
needed to deliver a pointer to an already committed mailbox event.  Mailbox
bytes, mailbox events, cursors and logical requests are owned by their existing
repositories and are never mutated here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, NoReturn

from taskcontroller.controlplane.mailbox_dispatch import MailboxDispatchOutcome
from taskcontroller.controlplane.wakeup_dispatch import PointerWakeupEmission
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
)
from taskcontroller.interaction.wakeup_gate import (
    WAKEUP_DUPLICATE,
    WAKEUP_EMITTED,
)
from taskcontroller.runtime.dispatch_ledger import DispatchCommitted


WAKEUP_OUTBOX_PROTOCOL = "dw.taskcontroller.wakeup-outbox/v1"
WAKEUP_INTENT_PENDING = "PENDING"
WAKEUP_INTENT_IN_FLIGHT = "IN_FLIGHT"
WAKEUP_INTENT_DELIVERED = "DELIVERED"
WAKEUP_INTENT_FAILED = "FAILED"
WAKEUP_INTENT_BLOCKED = "BLOCKED"

WAKEUP_ATTEMPT_STARTED = "STARTED"
WAKEUP_ATTEMPT_DELIVERED = "DELIVERED"
WAKEUP_ATTEMPT_FAILED = "FAILED"
WAKEUP_ATTEMPT_BLOCKED = "BLOCKED"

_INTENT_STATES = frozenset(
    {
        WAKEUP_INTENT_PENDING,
        WAKEUP_INTENT_IN_FLIGHT,
        WAKEUP_INTENT_DELIVERED,
        WAKEUP_INTENT_FAILED,
        WAKEUP_INTENT_BLOCKED,
    }
)
_ATTEMPT_STATES = frozenset(
    {
        WAKEUP_ATTEMPT_STARTED,
        WAKEUP_ATTEMPT_DELIVERED,
        WAKEUP_ATTEMPT_FAILED,
        WAKEUP_ATTEMPT_BLOCKED,
    }
)
_SHA256_PREFIX = "sha256:"


def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be a non-empty string")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, f"{name} must be an integer > 0")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, f"{name} must be an integer >= 0")
    return value


def _digest(value: Any, name: str) -> str:
    value = _required_text(value, name)
    if len(value) != len(_SHA256_PREFIX) + 64 or not value.startswith(_SHA256_PREFIX):
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, f"{name} is not a sha256 digest")
    try:
        int(value[len(_SHA256_PREFIX) :], 16)
    except ValueError as exc:
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, f"{name} is not a sha256 digest")
        raise AssertionError("_fail must raise") from exc
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"outbox key is not canonicalizable: {exc}")
        raise AssertionError("_fail must raise") from exc


def _logical_key(
    *,
    run_id: str,
    node_id: str,
    mailbox_ref: str,
    mailbox_seq: int,
    idempotency_key: str,
    recipient: str,
) -> str:
    material = _canonical_json(
        {
            "run_id": run_id,
            "node_id": node_id,
            "mailbox_ref": mailbox_ref,
            "mailbox_seq": mailbox_seq,
            "idempotency_key": idempotency_key,
            "recipient": recipient,
        }
    )
    return _SHA256_PREFIX + hashlib.sha256(material).hexdigest()


def _intent_id(logical_key: str) -> str:
    _digest(logical_key, "WakeupIntent.logical_key")
    return f"wakeup-intent:{logical_key[len(_SHA256_PREFIX) :]}"


def _validate_state(value: Any, allowed: frozenset[str], name: str) -> str:
    value = _required_text(value, name)
    if value not in allowed:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} is unsupported: {value!r}")
    return value


def _validate_retry_at(value: Any) -> str | None:
    return _optional_text(value, "retry_at")


@dataclass(frozen=True)
class WakeupIntent:
    """Immutable binding plus mutable delivery summary for one logical wake."""

    intent_id: str
    logical_key: str
    run_id: str
    node_id: str
    mailbox_ref: str
    mailbox_seq: int
    event_id: str
    event_digest: str
    envelope_digest: str
    message_id: str
    idempotency_key: str
    recipient: str
    state: str
    attempt_count: int
    next_attempt_at: str | None
    fallback: str | None
    claim_ttl_seconds: int | None
    created_at: str
    updated_at: str
    protocol: str = WAKEUP_OUTBOX_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != WAKEUP_OUTBOX_PROTOCOL:
            _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "unsupported WakeupIntent protocol")
        for name in (
            "intent_id",
            "run_id",
            "node_id",
            "mailbox_ref",
            "event_id",
            "message_id",
            "idempotency_key",
            "created_at",
            "updated_at",
        ):
            _required_text(getattr(self, name), f"WakeupIntent.{name}")
        _digest(self.logical_key, "WakeupIntent.logical_key")
        _digest(self.event_digest, "WakeupIntent.event_digest")
        _digest(self.envelope_digest, "WakeupIntent.envelope_digest")
        _non_negative_int(self.mailbox_seq, "WakeupIntent.mailbox_seq")
        if self.intent_id != _intent_id(self.logical_key):
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "WakeupIntent ID is not bound to logical key")
        expected_key = _logical_key(
            run_id=self.run_id,
            node_id=self.node_id,
            mailbox_ref=self.mailbox_ref,
            mailbox_seq=self.mailbox_seq,
            idempotency_key=self.idempotency_key,
            recipient=self.recipient,
        )
        if self.logical_key != expected_key:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "WakeupIntent logical key binding differs")
        _required_text(self.recipient, "WakeupIntent.recipient")
        _validate_state(self.state, _INTENT_STATES, "WakeupIntent.state")
        _non_negative_int(self.attempt_count, "WakeupIntent.attempt_count")
        _validate_retry_at(self.next_attempt_at)
        _optional_text(self.fallback, "WakeupIntent.fallback")
        if self.claim_ttl_seconds is not None:
            _positive_int(self.claim_ttl_seconds, "WakeupIntent.claim_ttl_seconds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "record_type": "WakeupIntent",
            "intent_id": self.intent_id,
            "logical_key": self.logical_key,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "mailbox_ref": self.mailbox_ref,
            "mailbox_seq": self.mailbox_seq,
            "event_id": self.event_id,
            "event_digest": self.event_digest,
            "envelope_digest": self.envelope_digest,
            "message_id": self.message_id,
            "idempotency_key": self.idempotency_key,
            "recipient": self.recipient,
            "state": self.state,
            "attempt_count": self.attempt_count,
            "next_attempt_at": self.next_attempt_at,
            "fallback": self.fallback,
            "claim_ttl_seconds": self.claim_ttl_seconds,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WakeupIntent":
        if not isinstance(payload, Mapping):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "WakeupIntent must be an object")
        if payload.get("protocol") != WAKEUP_OUTBOX_PROTOCOL or payload.get("record_type") != "WakeupIntent":
            _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "unsupported WakeupIntent record")
        try:
            return cls(
                intent_id=payload["intent_id"],
                logical_key=payload["logical_key"],
                run_id=payload["run_id"],
                node_id=payload["node_id"],
                mailbox_ref=payload["mailbox_ref"],
                mailbox_seq=payload["mailbox_seq"],
                event_id=payload["event_id"],
                event_digest=payload["event_digest"],
                envelope_digest=payload["envelope_digest"],
                message_id=payload["message_id"],
                idempotency_key=payload["idempotency_key"],
                recipient=payload["recipient"],
                state=payload["state"],
                attempt_count=payload["attempt_count"],
                next_attempt_at=payload["next_attempt_at"],
                fallback=payload["fallback"],
                claim_ttl_seconds=payload["claim_ttl_seconds"],
                created_at=payload["created_at"],
                updated_at=payload["updated_at"],
                protocol=payload["protocol"],
            )
        except KeyError as exc:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "WakeupIntent is missing a required field")
            raise AssertionError("_fail must raise") from exc


@dataclass(frozen=True)
class WakeupDeliveryAttempt:
    """Append-only delivery-attempt evidence stored outside mailbox state."""

    attempt_id: str
    intent_id: str
    attempt_number: int
    state: str
    attempted_at: str
    retry_at: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    protocol: str = WAKEUP_OUTBOX_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != WAKEUP_OUTBOX_PROTOCOL:
            _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "unsupported WakeupDeliveryAttempt protocol")
        _required_text(self.attempt_id, "WakeupDeliveryAttempt.attempt_id")
        _required_text(self.intent_id, "WakeupDeliveryAttempt.intent_id")
        _positive_int(self.attempt_number, "WakeupDeliveryAttempt.attempt_number")
        _validate_state(self.state, _ATTEMPT_STATES, "WakeupDeliveryAttempt.state")
        _required_text(self.attempted_at, "WakeupDeliveryAttempt.attempted_at")
        _validate_retry_at(self.retry_at)
        _optional_text(self.error_code, "WakeupDeliveryAttempt.error_code")
        _optional_text(self.error_detail, "WakeupDeliveryAttempt.error_detail")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "record_type": "WakeupDeliveryAttempt",
            "attempt_id": self.attempt_id,
            "intent_id": self.intent_id,
            "attempt_number": self.attempt_number,
            "state": self.state,
            "attempted_at": self.attempted_at,
            "retry_at": self.retry_at,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WakeupDeliveryAttempt":
        if not isinstance(payload, Mapping):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "WakeupDeliveryAttempt must be an object")
        if payload.get("protocol") != WAKEUP_OUTBOX_PROTOCOL or payload.get("record_type") != "WakeupDeliveryAttempt":
            _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "unsupported WakeupDeliveryAttempt record")
        try:
            return cls(
                attempt_id=payload["attempt_id"],
                intent_id=payload["intent_id"],
                attempt_number=payload["attempt_number"],
                state=payload["state"],
                attempted_at=payload["attempted_at"],
                retry_at=payload["retry_at"],
                error_code=payload["error_code"],
                error_detail=payload["error_detail"],
                protocol=payload["protocol"],
            )
        except KeyError as exc:
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "WakeupDeliveryAttempt is missing a required field",
            )
            raise AssertionError("_fail must raise") from exc


class WakeupOutbox:
    """SQLite-backed intent and delivery-attempt store.

    The schema has no mailbox payload/event/cursor columns and the class accepts
    no mailbox repository.  This makes it mechanically impossible for delivery
    retries to rewrite a logical mailbox request through this boundary.
    """

    def __init__(self, db_path: str | Path) -> None:
        path = str(db_path)
        if not path:
            raise TaskControllerValidationError("WakeupOutbox requires a database path")
        self._connection = sqlite3.connect(path, timeout=30, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS wakeup_intents (
                intent_id TEXT PRIMARY KEY,
                logical_key TEXT NOT NULL UNIQUE,
                protocol TEXT NOT NULL,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                mailbox_ref TEXT NOT NULL,
                mailbox_seq INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                event_digest TEXT NOT NULL,
                envelope_digest TEXT NOT NULL,
                message_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                recipient TEXT NOT NULL,
                state TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                next_attempt_at TEXT,
                fallback TEXT,
                claim_ttl_seconds INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wakeup_delivery_attempts (
                attempt_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL,
                protocol TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                retry_at TEXT,
                error_code TEXT,
                error_detail TEXT,
                UNIQUE (intent_id, attempt_number),
                FOREIGN KEY (intent_id) REFERENCES wakeup_intents(intent_id)
            );
            CREATE INDEX IF NOT EXISTS idx_wakeup_attempts_intent
                ON wakeup_delivery_attempts (intent_id, attempt_number);
            """
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "WakeupOutbox":
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()

    def create_intent(
        self,
        outcome: MailboxDispatchOutcome,
        emission: PointerWakeupEmission,
        *,
        recipient: str,
        created_at: str,
        retry_at: str | None = None,
        fallback: str | None = None,
        claim_ttl_seconds: int | None = None,
    ) -> WakeupIntent:
        """Insert or read one intent after verified mailbox commit evidence."""

        committed = self._validate_committed_pointer(
            outcome,
            emission,
            recipient=recipient,
        )
        recipient = _required_text(recipient, "WakeupIntent.recipient")
        created_at = _required_text(created_at, "WakeupIntent.created_at")
        retry_at = _validate_retry_at(retry_at)
        fallback = _optional_text(fallback, "WakeupIntent.fallback")
        if claim_ttl_seconds is not None:
            _positive_int(claim_ttl_seconds, "WakeupIntent.claim_ttl_seconds")

        logical_key = _logical_key(
            run_id=committed.run_id,
            node_id=committed.node_id,
            mailbox_ref=committed.mailbox_ref,
            mailbox_seq=committed.mailbox_seq,
            idempotency_key=committed.idempotency_key,
            recipient=recipient,
        )
        candidate = WakeupIntent(
            intent_id=_intent_id(logical_key),
            logical_key=logical_key,
            run_id=committed.run_id,
            node_id=committed.node_id,
            mailbox_ref=committed.mailbox_ref,
            mailbox_seq=committed.mailbox_seq,
            event_id=committed.event_id,
            event_digest=committed.event_digest,
            envelope_digest=committed.envelope_digest,
            message_id=committed.message_id,
            idempotency_key=committed.idempotency_key,
            recipient=recipient,
            state=WAKEUP_INTENT_PENDING,
            attempt_count=0,
            next_attempt_at=retry_at,
            fallback=fallback,
            claim_ttl_seconds=claim_ttl_seconds,
            created_at=created_at,
            updated_at=created_at,
        )

        self._begin()
        try:
            row = self._connection.execute(
                "SELECT * FROM wakeup_intents WHERE logical_key = ?",
                (candidate.logical_key,),
            ).fetchone()
            if row is not None:
                existing = self._intent_from_row(row)
                self._assert_same_intent_binding(existing, candidate)
                self._connection.commit()
                return existing
            self._connection.execute(
                """
                INSERT INTO wakeup_intents (
                    intent_id, logical_key, protocol, run_id, node_id, mailbox_ref,
                    mailbox_seq, event_id, event_digest, envelope_digest, message_id,
                    idempotency_key, recipient, state, attempt_count, next_attempt_at,
                    fallback, claim_ttl_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.intent_id,
                    candidate.logical_key,
                    candidate.protocol,
                    candidate.run_id,
                    candidate.node_id,
                    candidate.mailbox_ref,
                    candidate.mailbox_seq,
                    candidate.event_id,
                    candidate.event_digest,
                    candidate.envelope_digest,
                    candidate.message_id,
                    candidate.idempotency_key,
                    candidate.recipient,
                    candidate.state,
                    candidate.attempt_count,
                    candidate.next_attempt_at,
                    candidate.fallback,
                    candidate.claim_ttl_seconds,
                    candidate.created_at,
                    candidate.updated_at,
                ),
            )
            stored = self._intent_from_row(
                self._connection.execute(
                    "SELECT * FROM wakeup_intents WHERE intent_id = ?",
                    (candidate.intent_id,),
                ).fetchone()
            )
            if stored != candidate:
                _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "WakeupIntent exact readback differs")
            self._connection.commit()
            return stored
        except Exception:
            self._connection.rollback()
            raise

    def get_intent(self, intent_id: str) -> WakeupIntent:
        intent_id = _required_text(intent_id, "WakeupOutbox.intent_id")
        row = self._connection.execute(
            "SELECT * FROM wakeup_intents WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise TaskControllerValidationError(f"WakeupIntent not found: {intent_id}")
        return self._intent_from_row(row)

    def list_intents(self) -> tuple[WakeupIntent, ...]:
        rows = self._connection.execute(
            "SELECT * FROM wakeup_intents ORDER BY intent_id"
        ).fetchall()
        return tuple(self._intent_from_row(row) for row in rows)

    def record_delivery_attempt(
        self,
        intent_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        state: str,
        attempted_at: str,
        retry_at: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> WakeupDeliveryAttempt:
        """Append one idempotent delivery attempt without touching the mailbox."""

        intent_id = _required_text(intent_id, "WakeupDeliveryAttempt.intent_id")
        candidate = WakeupDeliveryAttempt(
            attempt_id=attempt_id,
            intent_id=intent_id,
            attempt_number=attempt_number,
            state=state,
            attempted_at=attempted_at,
            retry_at=retry_at,
            error_code=error_code,
            error_detail=error_detail,
        )

        self._begin()
        try:
            intent_row = self._connection.execute(
                "SELECT * FROM wakeup_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if intent_row is None:
                _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "delivery attempt references no WakeupIntent")

            existing_id_row = self._connection.execute(
                "SELECT * FROM wakeup_delivery_attempts WHERE attempt_id = ?",
                (candidate.attempt_id,),
            ).fetchone()
            if existing_id_row is not None:
                existing = self._attempt_from_row(existing_id_row)
                if existing != candidate:
                    _fail(
                        MailboxV2ErrorCode.DIGEST_MISMATCH,
                        "delivery attempt ID is bound to conflicting evidence",
                    )
                self._connection.commit()
                return existing

            existing_number_row = self._connection.execute(
                """
                SELECT * FROM wakeup_delivery_attempts
                WHERE intent_id = ? AND attempt_number = ?
                """,
                (candidate.intent_id, candidate.attempt_number),
            ).fetchone()
            if existing_number_row is not None:
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    "delivery attempt number is already occupied by another attempt",
                )

            max_number = self._connection.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) AS max_number
                FROM wakeup_delivery_attempts WHERE intent_id = ?
                """,
                (candidate.intent_id,),
            ).fetchone()["max_number"]
            if candidate.attempt_number != int(max_number) + 1:
                _fail(
                    MailboxV2ErrorCode.INVALID_SEQUENCE,
                    "delivery attempts must append in contiguous order",
                )

            self._connection.execute(
                """
                INSERT INTO wakeup_delivery_attempts (
                    attempt_id, intent_id, protocol, attempt_number, state,
                    attempted_at, retry_at, error_code, error_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.attempt_id,
                    candidate.intent_id,
                    candidate.protocol,
                    candidate.attempt_number,
                    candidate.state,
                    candidate.attempted_at,
                    candidate.retry_at,
                    candidate.error_code,
                    candidate.error_detail,
                ),
            )
            intent = self._intent_from_row(intent_row)
            updated_state = {
                WAKEUP_ATTEMPT_STARTED: WAKEUP_INTENT_IN_FLIGHT,
                WAKEUP_ATTEMPT_DELIVERED: WAKEUP_INTENT_DELIVERED,
                WAKEUP_ATTEMPT_FAILED: WAKEUP_INTENT_FAILED,
                WAKEUP_ATTEMPT_BLOCKED: WAKEUP_INTENT_BLOCKED,
            }[candidate.state]
            self._connection.execute(
                """
                UPDATE wakeup_intents
                SET state = ?, attempt_count = ?, next_attempt_at = ?, updated_at = ?
                WHERE intent_id = ?
                """,
                (
                    updated_state,
                    candidate.attempt_number,
                    candidate.retry_at,
                    candidate.attempted_at,
                    intent.intent_id,
                ),
            )
            stored_attempt = self._attempt_from_row(
                self._connection.execute(
                    "SELECT * FROM wakeup_delivery_attempts WHERE attempt_id = ?",
                    (candidate.attempt_id,),
                ).fetchone()
            )
            if stored_attempt != candidate:
                _fail(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "WakeupDeliveryAttempt exact readback differs",
                )
            stored_intent = self._intent_from_row(
                self._connection.execute(
                    "SELECT * FROM wakeup_intents WHERE intent_id = ?",
                    (intent.intent_id,),
                ).fetchone()
            )
            if stored_intent.attempt_count != candidate.attempt_number:
                _fail(
                    MailboxV2ErrorCode.DIGEST_MISMATCH,
                    "WakeupIntent attempt summary exact readback differs",
                )
            self._connection.commit()
            return stored_attempt
        except Exception:
            self._connection.rollback()
            raise

    def list_attempts(self, intent_id: str) -> tuple[WakeupDeliveryAttempt, ...]:
        intent_id = _required_text(intent_id, "WakeupOutbox.intent_id")
        rows = self._connection.execute(
            """
            SELECT * FROM wakeup_delivery_attempts
            WHERE intent_id = ? ORDER BY attempt_number
            """,
            (intent_id,),
        ).fetchall()
        return tuple(self._attempt_from_row(row) for row in rows)

    def prepare_retry(self, intent_id: str, *, retry_at: str) -> WakeupIntent:
        """Reset only outbox delivery state; return the same logical intent."""

        intent_id = _required_text(intent_id, "WakeupOutbox.intent_id")
        retry_at = _required_text(retry_at, "WakeupOutbox.retry_at")
        self._begin()
        try:
            row = self._connection.execute(
                "SELECT * FROM wakeup_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if row is None:
                raise TaskControllerValidationError(f"WakeupIntent not found: {intent_id}")
            current = self._intent_from_row(row)
            if current.state == WAKEUP_INTENT_DELIVERED:
                self._connection.commit()
                return current
            self._connection.execute(
                """
                UPDATE wakeup_intents
                SET state = ?, next_attempt_at = ?, updated_at = ?
                WHERE intent_id = ?
                """,
                (WAKEUP_INTENT_PENDING, retry_at, retry_at, intent_id),
            )
            stored = self._intent_from_row(
                self._connection.execute(
                    "SELECT * FROM wakeup_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
            )
            if (
                stored.intent_id != current.intent_id
                or stored.mailbox_ref != current.mailbox_ref
                or stored.mailbox_seq != current.mailbox_seq
                or stored.event_id != current.event_id
                or stored.event_digest != current.event_digest
                or stored.envelope_digest != current.envelope_digest
                or stored.idempotency_key != current.idempotency_key
                or stored.attempt_count != current.attempt_count
                or stored.state != WAKEUP_INTENT_PENDING
                or stored.next_attempt_at != retry_at
            ):
                _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "retry changed logical WakeupIntent binding")
            self._connection.commit()
            return stored
        except Exception:
            self._connection.rollback()
            raise

    @staticmethod
    def _validate_committed_pointer(
        outcome: MailboxDispatchOutcome,
        emission: PointerWakeupEmission,
        *,
        recipient: str,
    ) -> DispatchCommitted:
        if not isinstance(outcome, MailboxDispatchOutcome):
            raise TaskControllerValidationError(
                "WakeupIntent requires MailboxDispatchOutcome exact-readback evidence"
            )
        if not isinstance(emission, PointerWakeupEmission):
            raise TaskControllerValidationError(
                "WakeupIntent requires PointerWakeupEmission evidence"
            )
        recipient = _required_text(recipient, "WakeupIntent.recipient")
        committed = outcome.committed
        if not isinstance(committed, DispatchCommitted) or committed.readback_verified is not True:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "WakeupIntent requires a readback-verified DispatchCommitted",
            )
        decision = emission.decision
        if decision.status not in {WAKEUP_EMITTED, WAKEUP_DUPLICATE}:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "unsupported pointer wakeup decision")
        if (
            decision.dispatch_id != committed.committed_id
            or decision.mailbox_ref != committed.mailbox_ref
            or decision.mailbox_seq != committed.mailbox_seq
            or decision.envelope_digest != committed.envelope_digest
            or decision.event_digest != committed.event_digest
        ):
            _fail(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "pointer wakeup evidence differs from committed mailbox event",
            )
        signal = decision.signal
        if decision.status == WAKEUP_EMITTED:
            if signal is None:
                _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "emitted pointer wakeup has no signal")
            if (
                signal.run_id != committed.run_id
                or signal.recipient != recipient
                or signal.mailbox_ref != committed.mailbox_ref
                or signal.seq != committed.mailbox_seq + 1
            ):
                _fail(
                    MailboxV2ErrorCode.CONTRACT_MISMATCH,
                    "pointer wakeup signal differs from committed mailbox event",
                )
        elif signal is not None:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "duplicate pointer wakeup carries a signal")
        return committed

    def _begin(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _intent_from_row(row: sqlite3.Row | None) -> WakeupIntent:
        if row is None:
            raise TaskControllerValidationError("WakeupIntent exact readback returned no row")
        return WakeupIntent.from_dict(dict(row) | {"record_type": "WakeupIntent"})

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row | None) -> WakeupDeliveryAttempt:
        if row is None:
            raise TaskControllerValidationError("WakeupDeliveryAttempt exact readback returned no row")
        return WakeupDeliveryAttempt.from_dict(dict(row) | {"record_type": "WakeupDeliveryAttempt"})

    @staticmethod
    def _assert_same_intent_binding(existing: WakeupIntent, candidate: WakeupIntent) -> None:
        immutable_fields = (
            "intent_id",
            "logical_key",
            "run_id",
            "node_id",
            "mailbox_ref",
            "mailbox_seq",
            "event_id",
            "event_digest",
            "envelope_digest",
            "message_id",
            "idempotency_key",
            "recipient",
            "fallback",
            "claim_ttl_seconds",
        )
        if any(getattr(existing, field) != getattr(candidate, field) for field in immutable_fields):
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "duplicate WakeupIntent key is bound to conflicting evidence",
            )


__all__ = [
    "WAKEUP_ATTEMPT_BLOCKED",
    "WAKEUP_ATTEMPT_DELIVERED",
    "WAKEUP_ATTEMPT_FAILED",
    "WAKEUP_ATTEMPT_STARTED",
    "WAKEUP_INTENT_BLOCKED",
    "WAKEUP_INTENT_DELIVERED",
    "WAKEUP_INTENT_FAILED",
    "WAKEUP_INTENT_IN_FLIGHT",
    "WAKEUP_INTENT_PENDING",
    "WAKEUP_OUTBOX_PROTOCOL",
    "WakeupDeliveryAttempt",
    "WakeupIntent",
    "WakeupOutbox",
]
