"""Dispatch prepare/commit protocol for the mailbox/v2 boundary.

The Run Ledger and mailbox have separate authorities and cannot be committed
atomically by this reference implementation.  This module makes the ordering
explicit: record ``DispatchPrepared``, append one mailbox event through the
repository CAS boundary, exact-read it back, and only then record
``DispatchCommitted``.  Wakeup emission is deliberately implemented by the
separate ``interaction.wakeup_gate`` module.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, NoReturn, Protocol

from taskcontroller.audit.event import AuditEvent
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import MailboxRepository
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
)


DISPATCH_PROTOCOL = "dw.taskcontroller.dispatch/v1"
DISPATCH_PREPARED = "DISPATCH_PREPARED"
DISPATCH_COMMITTED = "DISPATCH_COMMITTED"
DISPATCH_SOURCE = "taskcontroller.runtime.dispatch_ledger"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be a non-empty string")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, f"{name} must be an integer >= 0")
    return value


def _sequence_or_initial(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, f"{name} must be an integer >= -1")
    return value


def _digest(value: Any, name: str) -> str:
    value = _required_text(value, name)
    if _SHA256_RE.fullmatch(value) is None:
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, f"{name} is not a sha256 digest")
    return value


@dataclass(frozen=True)
class DispatchIdentity:
    """Immutable logical request and current-generation identity binding."""

    run_id: str
    node_id: str
    plan_version: str
    contract_digest: str
    boundary_digest: str
    source_digest: str
    attempt_id: str
    lease_generation: int
    fencing_token: str
    message_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "node_id",
            "plan_version",
            "attempt_id",
            "fencing_token",
            "message_id",
            "idempotency_key",
        ):
            _required_text(getattr(self, name), f"logical_request.{name}")
        for name in ("contract_digest", "boundary_digest", "source_digest"):
            _digest(getattr(self, name), f"logical_request.{name}")
        if (
            isinstance(self.lease_generation, bool)
            or not isinstance(self.lease_generation, int)
            or self.lease_generation <= 0
        ):
            _fail(
                MailboxV2ErrorCode.STALE_GENERATION,
                "logical_request.lease_generation must be an integer > 0",
            )

    @classmethod
    def from_envelope(cls, envelope: V2MailboxEnvelope) -> "DispatchIdentity":
        if not isinstance(envelope, V2MailboxEnvelope):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch identity requires a v2 envelope")
        payload = envelope.to_dict()
        execution = payload["execution_identity"]
        return cls(
            run_id=payload["run_id"],
            node_id=payload["node_id"],
            plan_version=execution["plan_version"],
            contract_digest=execution["contract_digest"],
            boundary_digest=execution["boundary_digest"],
            source_digest=execution["source_digest"],
            attempt_id=execution["attempt_id"],
            lease_generation=execution["lease_generation"],
            fencing_token=execution["fencing_token"],
            message_id=payload["message_id"],
            idempotency_key=payload["idempotency_key"],
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DispatchIdentity":
        if not isinstance(payload, Mapping):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "logical_request must be an object")
        try:
            return cls(
                run_id=payload["run_id"],
                node_id=payload["node_id"],
                plan_version=payload["plan_version"],
                contract_digest=payload["contract_digest"],
                boundary_digest=payload["boundary_digest"],
                source_digest=payload["source_digest"],
                attempt_id=payload["attempt_id"],
                lease_generation=payload["lease_generation"],
                fencing_token=payload["fencing_token"],
                message_id=payload["message_id"],
                idempotency_key=payload["idempotency_key"],
            )
        except KeyError as exc:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "logical_request is missing a required field")
            raise AssertionError("_fail must raise") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "plan_version": self.plan_version,
            "contract_digest": self.contract_digest,
            "boundary_digest": self.boundary_digest,
            "source_digest": self.source_digest,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
            "fencing_token": self.fencing_token,
            "message_id": self.message_id,
            "idempotency_key": self.idempotency_key,
        }

    def execution_identity(self) -> dict[str, Any]:
        """Return only fields accepted by ``V2MailboxEnvelope`` identity checks."""

        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "plan_version": self.plan_version,
            "contract_digest": self.contract_digest,
            "boundary_digest": self.boundary_digest,
            "source_digest": self.source_digest,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
            "fencing_token": self.fencing_token,
        }


@dataclass(frozen=True)
class DispatchPrepared:
    """Run Ledger state before any mailbox mutation is attempted."""

    identity: DispatchIdentity
    state_version: int
    mailbox_ref: str
    expected_mailbox_seq: int
    envelope_digest: str
    prepared_id: str
    prepared_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DispatchIdentity):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchPrepared identity is invalid")
        _non_negative_int(self.state_version, "DispatchPrepared.state_version")
        _required_text(self.mailbox_ref, "DispatchPrepared.mailbox_ref")
        _sequence_or_initial(self.expected_mailbox_seq, "DispatchPrepared.expected_mailbox_seq")
        _digest(self.envelope_digest, "DispatchPrepared.envelope_digest")
        _required_text(self.prepared_id, "DispatchPrepared.prepared_id")
        _required_text(self.prepared_at, "DispatchPrepared.prepared_at")

    @property
    def run_id(self) -> str:
        return self.identity.run_id

    @property
    def node_id(self) -> str:
        return self.identity.node_id

    @property
    def lease_generation(self) -> int:
        return self.identity.lease_generation

    @property
    def message_id(self) -> str:
        return self.identity.message_id

    @property
    def idempotency_key(self) -> str:
        return self.identity.idempotency_key

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": DISPATCH_PROTOCOL,
            "record_type": "DispatchPrepared",
            "prepared_id": self.prepared_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "state_version": self.state_version,
            "lease_generation": self.lease_generation,
            "mailbox_ref": self.mailbox_ref,
            "expected_mailbox_seq": self.expected_mailbox_seq,
            "envelope_digest": self.envelope_digest,
            "logical_request": self.identity.to_dict(),
            "prepared_at": self.prepared_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DispatchPrepared":
        if not isinstance(payload, Mapping):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchPrepared record must be an object")
        if payload.get("protocol") != DISPATCH_PROTOCOL or payload.get("record_type") != "DispatchPrepared":
            _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "unsupported DispatchPrepared record")
        try:
            identity = DispatchIdentity.from_dict(payload["logical_request"])
            result = cls(
                identity=identity,
                state_version=payload["state_version"],
                mailbox_ref=payload["mailbox_ref"],
                expected_mailbox_seq=payload["expected_mailbox_seq"],
                envelope_digest=payload["envelope_digest"],
                prepared_id=payload["prepared_id"],
                prepared_at=payload["prepared_at"],
            )
        except KeyError as exc:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchPrepared record is missing a required field")
            raise AssertionError("_fail must raise") from exc
        if result.run_id != payload.get("run_id") or result.node_id != payload.get("node_id"):
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "DispatchPrepared run/node binding differs")
        if result.lease_generation != payload.get("lease_generation"):
            _fail(MailboxV2ErrorCode.STALE_GENERATION, "DispatchPrepared generation binding differs")
        return result


@dataclass(frozen=True)
class DispatchCommitted:
    """Run Ledger state proven by a mailbox CAS write and exact readback."""

    prepared_id: str
    identity: DispatchIdentity
    state_version: int
    mailbox_ref: str
    expected_mailbox_seq: int
    mailbox_seq: int
    event_id: str
    message_id: str
    envelope_digest: str
    event_digest: str
    readback_verified: bool
    committed_id: str
    committed_at: str

    def __post_init__(self) -> None:
        _required_text(self.prepared_id, "DispatchCommitted.prepared_id")
        if not isinstance(self.identity, DispatchIdentity):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchCommitted identity is invalid")
        _non_negative_int(self.state_version, "DispatchCommitted.state_version")
        _required_text(self.mailbox_ref, "DispatchCommitted.mailbox_ref")
        _sequence_or_initial(self.expected_mailbox_seq, "DispatchCommitted.expected_mailbox_seq")
        _non_negative_int(self.mailbox_seq, "DispatchCommitted.mailbox_seq")
        if self.mailbox_seq != self.expected_mailbox_seq + 1:
            _fail(
                MailboxV2ErrorCode.INVALID_SEQUENCE,
                "DispatchCommitted mailbox sequence is not the prepared successor",
            )
        _required_text(self.event_id, "DispatchCommitted.event_id")
        _required_text(self.message_id, "DispatchCommitted.message_id")
        if self.message_id != self.identity.message_id:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "DispatchCommitted message identity differs")
        _digest(self.envelope_digest, "DispatchCommitted.envelope_digest")
        _digest(self.event_digest, "DispatchCommitted.event_digest")
        if self.readback_verified is not True:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "DispatchCommitted requires verified exact readback",
            )
        _required_text(self.committed_id, "DispatchCommitted.committed_id")
        _required_text(self.committed_at, "DispatchCommitted.committed_at")

    @property
    def run_id(self) -> str:
        return self.identity.run_id

    @property
    def node_id(self) -> str:
        return self.identity.node_id

    @property
    def lease_generation(self) -> int:
        return self.identity.lease_generation

    @property
    def idempotency_key(self) -> str:
        return self.identity.idempotency_key

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": DISPATCH_PROTOCOL,
            "record_type": "DispatchCommitted",
            "prepared_id": self.prepared_id,
            "committed_id": self.committed_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "state_version": self.state_version,
            "lease_generation": self.lease_generation,
            "mailbox_ref": self.mailbox_ref,
            "expected_mailbox_seq": self.expected_mailbox_seq,
            "mailbox_seq": self.mailbox_seq,
            "event_id": self.event_id,
            "message_id": self.message_id,
            "envelope_digest": self.envelope_digest,
            "event_digest": self.event_digest,
            "readback_verified": self.readback_verified,
            "logical_request": self.identity.to_dict(),
            "committed_at": self.committed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DispatchCommitted":
        if not isinstance(payload, Mapping):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchCommitted record must be an object")
        if payload.get("protocol") != DISPATCH_PROTOCOL or payload.get("record_type") != "DispatchCommitted":
            _fail(MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL, "unsupported DispatchCommitted record")
        try:
            identity = DispatchIdentity.from_dict(payload["logical_request"])
            result = cls(
                prepared_id=payload["prepared_id"],
                identity=identity,
                state_version=payload["state_version"],
                mailbox_ref=payload["mailbox_ref"],
                expected_mailbox_seq=payload["expected_mailbox_seq"],
                mailbox_seq=payload["mailbox_seq"],
                event_id=payload["event_id"],
                message_id=payload["message_id"],
                envelope_digest=payload["envelope_digest"],
                event_digest=payload["event_digest"],
                readback_verified=payload["readback_verified"],
                committed_id=payload["committed_id"],
                committed_at=payload["committed_at"],
            )
        except KeyError as exc:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchCommitted record is missing a required field")
            raise AssertionError("_fail must raise") from exc
        if result.run_id != payload.get("run_id") or result.node_id != payload.get("node_id"):
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "DispatchCommitted run/node binding differs")
        if result.lease_generation != payload.get("lease_generation"):
            _fail(MailboxV2ErrorCode.STALE_GENERATION, "DispatchCommitted generation binding differs")
        return result


class DispatchLedger(Protocol):
    """Minimal ledger sink/readback surface accepted by the protocol."""

    def record(self, run_id: str, event: AuditEvent) -> int:
        ...

    def events(self, run_id: str) -> list[AuditEvent]:
        ...


class DispatchProtocol:
    """Run Ledger/mailbox prepare-commit coordinator.

    ``repository`` is the only mailbox mutation boundary.  ``ledger`` may be an
    ``AuditFacade`` or the underlying ``SQLiteRunLedger``; both are supported so
    this protocol remains transport-neutral while using the existing durable
    append path.
    """

    def __init__(self, *, repository: MailboxRepository, ledger: Any, actor: str = "controller") -> None:
        if not isinstance(repository, MailboxRepository):
            raise TaskControllerValidationError("DispatchProtocol requires a MailboxRepository")
        if not callable(getattr(ledger, "record", None)) and not callable(getattr(ledger, "append", None)):
            raise TaskControllerValidationError("DispatchProtocol ledger must provide record or append")
        self._repository = repository
        self._ledger = ledger
        self._actor = _required_text(actor, "DispatchProtocol.actor")
        self._prepared: dict[tuple[str, str], DispatchPrepared] = {}
        self._committed: dict[tuple[str, str], DispatchCommitted] = {}

    @property
    def repository(self) -> MailboxRepository:
        return self._repository

    @property
    def ledger(self) -> Any:
        return self._ledger

    def prepare(
        self,
        envelope: V2MailboxEnvelope,
        *,
        mailbox_ref: str,
        expected_mailbox_seq: int,
        state_version: int,
        lease_generation: int,
        prepared_at: str,
    ) -> DispatchPrepared:
        """Record ``DispatchPrepared`` before attempting mailbox CAS."""

        if not isinstance(envelope, V2MailboxEnvelope):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchProtocol.prepare requires a v2 envelope")
        identity = DispatchIdentity.from_envelope(envelope)
        if identity.lease_generation != lease_generation:
            _fail(MailboxV2ErrorCode.STALE_GENERATION, "prepared generation does not match envelope")
        prepared = DispatchPrepared(
            identity=identity,
            state_version=state_version,
            mailbox_ref=mailbox_ref,
            expected_mailbox_seq=expected_mailbox_seq,
            envelope_digest=envelope.digest(),
            prepared_id=f"dispatch-prepared:{envelope.digest()}",
            prepared_at=prepared_at,
        )
        key = (prepared.run_id, prepared.idempotency_key)
        cached = self._prepared.get(key)
        if cached is not None:
            self._assert_same_prepared(cached, prepared)
            return cached

        existing_event = self._find_event(prepared.run_id, prepared.prepared_id)
        if existing_event is not None:
            existing = self._prepared_from_event(existing_event)
            self._assert_same_prepared(existing, prepared)
            self._prepared[key] = existing
            return existing

        event = self._prepared_event(prepared)
        self._append_or_readback(event)
        self._prepared[key] = prepared
        return prepared

    def dispatch(
        self,
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
        *,
        committed_at: str,
    ) -> DispatchCommitted:
        """CAS-write, exact-readback, then append ``DispatchCommitted``."""

        if not isinstance(prepared, DispatchPrepared):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch requires DispatchPrepared")
        if not isinstance(envelope, V2MailboxEnvelope):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch requires a v2 envelope")
        self._assert_envelope_matches(prepared, envelope)
        key = (prepared.run_id, prepared.idempotency_key)
        cached = self._committed.get(key)
        if cached is not None:
            return cached

        existing_event = self._find_event(
            prepared.run_id,
            f"dispatch-committed:{prepared.envelope_digest}",
        )
        if existing_event is not None:
            committed = self._committed_from_event(existing_event)
            self._assert_same_commit(prepared, envelope, committed)
            self._committed[key] = committed
            return committed

        receipt = self._repository.write(
            prepared.mailbox_ref,
            prepared.expected_mailbox_seq,
            envelope,
            expected_identity=prepared.identity.execution_identity(),
        )
        snapshot = self._repository.exact_readback(receipt)
        self._verify_exact_readback(prepared, envelope, receipt, snapshot)

        committed = DispatchCommitted(
            prepared_id=prepared.prepared_id,
            identity=prepared.identity,
            state_version=prepared.state_version,
            mailbox_ref=prepared.mailbox_ref,
            expected_mailbox_seq=prepared.expected_mailbox_seq,
            mailbox_seq=receipt.event_seq,
            event_id=receipt.event_id,
            message_id=receipt.message_id,
            envelope_digest=receipt.envelope_digest,
            event_digest=receipt.event_digest,
            readback_verified=True,
            committed_id=f"dispatch-committed:{prepared.envelope_digest}",
            committed_at=committed_at,
        )
        event = self._committed_event(committed)
        self._append_or_readback(event)
        self._committed[key] = committed
        return committed

    def _append_or_readback(self, event: AuditEvent) -> None:
        try:
            if callable(getattr(self._ledger, "record", None)):
                self._ledger.record(event.run_id, event)
            else:
                self._ledger.append(event.run_id, event)
        except ValueError:
            existing = self._find_event(event.run_id, event.event_id)
            if existing is None or existing.after.get("record") != event.after.get("record"):
                raise

    def _find_event(self, run_id: str, event_id: str) -> AuditEvent | None:
        reader = getattr(self._ledger, "events", None)
        if not callable(reader):
            return None
        return next((event for event in reader(run_id) if event.event_id == event_id), None)

    def _prepared_event(self, prepared: DispatchPrepared) -> AuditEvent:
        return AuditEvent(
            event_id=prepared.prepared_id,
            timestamp=prepared.prepared_at,
            run_id=prepared.run_id,
            source=DISPATCH_SOURCE,
            decision_kind=DISPATCH_PREPARED,
            node_id=prepared.node_id,
            actor=self._actor,
            payload_summary=f"DispatchPrepared {prepared.message_id}",
            before={"state": "READY", "state_version": prepared.state_version},
            after={"state": DISPATCH_PREPARED, "record": prepared.to_dict()},
            evidence_refs=(prepared.mailbox_ref,),
            annotations={"protocol": DISPATCH_PROTOCOL},
            version=1,
        )

    def _committed_event(self, committed: DispatchCommitted) -> AuditEvent:
        return AuditEvent(
            event_id=committed.committed_id,
            timestamp=committed.committed_at,
            run_id=committed.run_id,
            source=DISPATCH_SOURCE,
            decision_kind=DISPATCH_COMMITTED,
            node_id=committed.node_id,
            actor=self._actor,
            payload_summary=f"DispatchCommitted {committed.message_id}",
            before={
                "state": DISPATCH_PREPARED,
                "prepared_id": committed.prepared_id,
                "expected_mailbox_seq": committed.expected_mailbox_seq,
                "envelope_digest": committed.envelope_digest,
            },
            after={"state": DISPATCH_COMMITTED, "record": committed.to_dict()},
            evidence_refs=(
                committed.mailbox_ref,
                f"{committed.mailbox_ref}:event-{committed.event_id}",
            ),
            annotations={"protocol": DISPATCH_PROTOCOL, "exact_readback": True},
            version=1,
        )

    @staticmethod
    def _prepared_from_event(event: AuditEvent) -> DispatchPrepared:
        try:
            return DispatchPrepared.from_dict(event.after["record"])
        except (KeyError, TypeError) as exc:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchPrepared ledger record is malformed")
            raise AssertionError("_fail must raise") from exc

    @staticmethod
    def _committed_from_event(event: AuditEvent) -> DispatchCommitted:
        try:
            return DispatchCommitted.from_dict(event.after["record"])
        except (KeyError, TypeError) as exc:
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "DispatchCommitted ledger record is malformed")
            raise AssertionError("_fail must raise") from exc

    @staticmethod
    def _assert_same_prepared(left: DispatchPrepared, right: DispatchPrepared) -> None:
        if left.to_dict() != right.to_dict():
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "logical request was prepared with different bindings")

    @staticmethod
    def _assert_envelope_matches(prepared: DispatchPrepared, envelope: V2MailboxEnvelope) -> None:
        identity = DispatchIdentity.from_envelope(envelope)
        if identity != prepared.identity or envelope.digest() != prepared.envelope_digest:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "dispatch envelope differs from prepared identity/digest")

    @staticmethod
    def _assert_same_commit(
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
        committed: DispatchCommitted,
    ) -> None:
        if committed.prepared_id != prepared.prepared_id:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "committed record does not bind prepared record")
        if committed.identity != prepared.identity or committed.envelope_digest != envelope.digest():
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "committed record identity/digest differs")

    @staticmethod
    def _verify_exact_readback(
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
        receipt: Any,
        snapshot: Any,
    ) -> None:
        expected_digest = envelope.digest()
        if receipt.mailbox_ref != prepared.mailbox_ref:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "mailbox receipt ref differs from DispatchPrepared")
        if receipt.event_seq != prepared.expected_mailbox_seq + 1:
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "mailbox receipt sequence differs from prepared successor")
        if receipt.message_id != prepared.message_id:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "mailbox receipt message differs from prepared request")
        if receipt.envelope_digest != expected_digest:
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "mailbox receipt envelope digest differs")
        events = getattr(snapshot, "events", ())
        if not isinstance(events, (list, tuple)):
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "exact readback has no event collection")
        event = next((item for item in events if item.event_id == receipt.event_id), None)
        if event is None:
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "exact readback omitted the written event")
        if (
            event.mailbox_ref != prepared.mailbox_ref
            or event.event_seq != receipt.event_seq
            or event.envelope_digest != receipt.envelope_digest
            or event.event_digest != receipt.event_digest
            or event.envelope != envelope
        ):
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "exact readback event binding differs")


__all__ = [
    "DISPATCH_COMMITTED",
    "DISPATCH_PREPARED",
    "DISPATCH_PROTOCOL",
    "DispatchCommitted",
    "DispatchIdentity",
    "DispatchLedger",
    "DispatchPrepared",
    "DispatchProtocol",
]
