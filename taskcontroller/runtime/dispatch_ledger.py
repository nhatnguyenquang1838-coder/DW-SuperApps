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
from taskcontroller.interaction.mailbox_repository import (
    MailboxEvent,
    MailboxRepository,
    WriteReceipt,
)
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


RECONCILIATION_RETRY = "RETRY"
RECONCILIATION_REPAIR = "REPAIR"
RECONCILIATION_CONSUME = "CONSUME"
RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"

RECONCILIATION_PREPARED_NO_MAILBOX = "PREPARED_NO_MAILBOX"
RECONCILIATION_MAILBOX_COMMITTED_LEDGER_UNCOMMITTED = (
    "MAILBOX_COMMITTED_LEDGER_UNCOMMITTED"
)
RECONCILIATION_DISPATCH_COMMITTED = "DISPATCH_COMMITTED"
RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT = "IDENTITY_OR_DIGEST_CONFLICT"


@dataclass(frozen=True)
class ReconciliationDecision:
    """One deterministic recovery disposition for a dispatch boundary.

    A decision is deliberately small and serializable: it records the observed
    state, exactly one action, bounded reason text and references to durable
    evidence.  It never contains Slack/chat content or a second action plan.
    """

    state: str
    action: str
    reason: str
    evidence_refs: tuple[str, ...] = ()
    committed: DispatchCommitted | None = None
    blocked: bool = False

    def __post_init__(self) -> None:
        _required_text(self.state, "ReconciliationDecision.state")
        _required_text(self.action, "ReconciliationDecision.action")
        _required_text(self.reason, "ReconciliationDecision.reason")
        if self.action not in {
            RECONCILIATION_RETRY,
            RECONCILIATION_REPAIR,
            RECONCILIATION_CONSUME,
            RECONCILIATION_BLOCKED,
        }:
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                f"unsupported reconciliation action {self.action!r}",
            )
        if not isinstance(self.evidence_refs, (tuple, list)):
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "ReconciliationDecision.evidence_refs must be a sequence",
            )
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        for ref in self.evidence_refs:
            _required_text(ref, "ReconciliationDecision.evidence_refs item")
        if self.committed is not None and not isinstance(self.committed, DispatchCommitted):
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "ReconciliationDecision.committed is invalid",
            )
        expected_blocked = self.action == RECONCILIATION_BLOCKED
        if self.blocked is not expected_blocked:
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "blocked flag must match reconciliation action",
            )
        if expected_blocked and self.committed is not None:
            _fail(
                MailboxV2ErrorCode.CONTRACT_MISMATCH,
                "blocked reconciliation cannot expose committed evidence",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": DISPATCH_PROTOCOL,
            "record_type": "ReconciliationDecision",
            "state": self.state,
            "action": self.action,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "committed": self.committed.to_dict() if self.committed is not None else None,
            "blocked": self.blocked,
        }


class DispatchReconciler:
    """Reconstruct and repair one dispatch after a restart or crash.

    The reconciler reads the durable Run Ledger and the exact mailbox snapshot.
    It treats process-local ``DispatchProtocol`` caches as disposable.  A
    matching mailbox event is repaired into the ledger without another mailbox
    write; an empty successor slot is retried through the existing CAS boundary;
    an already complete pair is consumed without mutation; every ambiguity is
    blocked fail-closed.
    """

    def __init__(self, *, repository: MailboxRepository, ledger: Any, actor: str = "controller") -> None:
        if not isinstance(repository, MailboxRepository):
            raise TaskControllerValidationError("DispatchReconciler requires a MailboxRepository")
        if not callable(getattr(ledger, "record", None)) and not callable(getattr(ledger, "append", None)):
            raise TaskControllerValidationError("DispatchReconciler ledger must provide record or append")
        self._repository = repository
        self._ledger = ledger
        self._protocol = DispatchProtocol(repository=repository, ledger=ledger, actor=actor)

    def reconcile(
        self,
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
        *,
        reconciled_at: str,
    ) -> ReconciliationDecision:
        """Return and perform exactly one recovery action for ``prepared``."""

        if not isinstance(prepared, DispatchPrepared):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "reconcile requires DispatchPrepared")
        if not isinstance(envelope, V2MailboxEnvelope):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "reconcile requires a v2 envelope")
        try:
            self._protocol._assert_envelope_matches(prepared, envelope)
        except TaskControllerValidationError as exc:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                f"supplied envelope differs from prepared binding: {exc}",
            )

        try:
            ledger_events = self._ledger_events(prepared.run_id)
        except Exception as exc:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                f"durable ledger cannot be read: {exc}",
            )

        prepared_event = next(
            (event for event in ledger_events if event.event_id == prepared.prepared_id),
            None,
        )
        if prepared_event is None:
            return self._blocked(
                prepared,
                "MISSING_PREPARED",
                "durable DispatchPrepared record is absent",
            )
        if prepared_event.decision_kind != DISPATCH_PREPARED:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                "prepared event has an unexpected decision kind",
            )
        try:
            durable_prepared = DispatchPrepared.from_dict(prepared_event.after["record"])
            self._protocol._assert_same_prepared(durable_prepared, prepared)
        except (KeyError, TypeError, TaskControllerValidationError) as exc:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                f"durable DispatchPrepared binding is malformed or conflicting: {exc}",
            )

        try:
            snapshot = self._repository.read(prepared.mailbox_ref)
            events = self._validate_snapshot(snapshot, prepared)
        except Exception as exc:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                f"mailbox snapshot cannot be validated: {exc}",
            )

        exact_event, conflict = self._locate_event(events, prepared, envelope)
        if conflict is not None:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                conflict,
                event=exact_event,
            )

        committed = self._find_committed_record(ledger_events, prepared)
        if committed[1] is not None:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                committed[1],
                event=exact_event,
            )
        durable_committed = committed[0]

        if exact_event is not None:
            if durable_committed is not None:
                if not self._commit_matches_event(durable_committed, prepared, envelope, exact_event):
                    return self._blocked(
                        prepared,
                        RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                        "DispatchCommitted does not match the exact mailbox event",
                        event=exact_event,
                    )
                return ReconciliationDecision(
                    state=RECONCILIATION_DISPATCH_COMMITTED,
                    action=RECONCILIATION_CONSUME,
                    reason="exact mailbox event and DispatchCommitted evidence already exist",
                    evidence_refs=self._evidence_refs(prepared, exact_event, durable_committed),
                    committed=durable_committed,
                )

            try:
                repaired = self._commit_from_existing_event(
                    prepared,
                    envelope,
                    exact_event,
                    reconciled_at=reconciled_at,
                )
            except Exception as exc:
                return self._blocked(
                    prepared,
                    RECONCILIATION_MAILBOX_COMMITTED_LEDGER_UNCOMMITTED,
                    f"existing mailbox event could not repair the ledger: {exc}",
                    event=exact_event,
                )
            return ReconciliationDecision(
                state=RECONCILIATION_MAILBOX_COMMITTED_LEDGER_UNCOMMITTED,
                action=RECONCILIATION_REPAIR,
                reason="exact mailbox event was read back and committed into the ledger",
                evidence_refs=self._evidence_refs(prepared, exact_event, repaired),
                committed=repaired,
            )

        if durable_committed is not None:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                "DispatchCommitted exists but its exact mailbox event is absent",
            )

        if snapshot_last_event_seq(events) != prepared.expected_mailbox_seq:
            return self._blocked(
                prepared,
                RECONCILIATION_IDENTITY_OR_DIGEST_CONFLICT,
                "mailbox successor slot is not empty at the prepared sequence",
            )

        try:
            retried = self._protocol.dispatch(
                prepared,
                envelope,
                committed_at=reconciled_at,
            )
        except Exception as exc:
            return self._blocked(
                prepared,
                RECONCILIATION_PREPARED_NO_MAILBOX,
                f"retry did not produce verified committed evidence: {exc}",
            )
        return ReconciliationDecision(
            state=RECONCILIATION_PREPARED_NO_MAILBOX,
            action=RECONCILIATION_RETRY,
            reason="prepared successor slot was empty; CAS/exact-readback/commit was retried",
            evidence_refs=self._evidence_refs(prepared, None, retried),
            committed=retried,
        )

    def _ledger_events(self, run_id: str) -> list[AuditEvent]:
        events = self._ledger.events(run_id)
        if not isinstance(events, list):
            events = list(events)
        return events

    @staticmethod
    def _validate_snapshot(snapshot: Any, prepared: DispatchPrepared) -> tuple[MailboxEvent, ...]:
        if getattr(snapshot, "mailbox_ref", None) != prepared.mailbox_ref:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "mailbox snapshot reference differs")
        events = getattr(snapshot, "events", None)
        if not isinstance(events, (list, tuple)):
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "mailbox snapshot has no event collection")
        validated = tuple(events)
        for expected_seq, event in enumerate(validated):
            if not isinstance(event, MailboxEvent):
                _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "mailbox snapshot contains a non-event")
            if event.event_seq != expected_seq:
                _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "mailbox event sequence has a gap")
            if event.mailbox_ref != prepared.mailbox_ref:
                _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "mailbox event reference differs")
            if not isinstance(event.envelope, V2MailboxEnvelope):
                _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "mailbox event envelope is invalid")
        if getattr(snapshot, "last_event_seq", None) != snapshot_last_event_seq(validated):
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "mailbox snapshot last sequence is inconsistent")
        return validated

    @staticmethod
    def _locate_event(
        events: tuple[MailboxEvent, ...],
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
    ) -> tuple[MailboxEvent | None, str | None]:
        expected_event_seq = prepared.expected_mailbox_seq + 1
        exact: MailboxEvent | None = None
        conflict: MailboxEvent | None = None
        for event in events:
            message_id = event.envelope.to_dict().get("message_id")
            related = (
                event.event_seq == expected_event_seq
                or event.idempotency_key == prepared.idempotency_key
                or message_id == prepared.message_id
            )
            try:
                identity = DispatchIdentity.from_envelope(event.envelope)
            except TaskControllerValidationError:
                identity = None
            is_exact = (
                identity == prepared.identity
                and event.event_seq == expected_event_seq
                and event.logical_seq == envelope.seq
                and event.producer_namespace == envelope.producer_namespace
                and event.idempotency_key == envelope.idempotency_key
                and event.envelope_digest == envelope.digest()
                and event.envelope == envelope
            )
            if is_exact:
                if exact is not None:
                    return exact, "multiple mailbox events match one prepared dispatch"
                exact = event
            elif related:
                conflict = event
        if conflict is not None:
            return exact, (
                "mailbox event conflicts with the prepared identity/digest or occupies the "
                f"successor slot: {conflict.event_id}"
            )
        return exact, None

    @staticmethod
    def _find_committed_record(
        ledger_events: list[AuditEvent],
        prepared: DispatchPrepared,
    ) -> tuple[DispatchCommitted | None, str | None]:
        expected_id = f"dispatch-committed:{prepared.envelope_digest}"
        for event in ledger_events:
            if event.decision_kind != DISPATCH_COMMITTED:
                continue
            record = event.after.get("record") if isinstance(event.after, Mapping) else None
            candidate_for_dispatch = event.event_id == expected_id or (
                isinstance(record, Mapping) and record.get("prepared_id") == prepared.prepared_id
            )
            if not candidate_for_dispatch:
                continue
            try:
                committed = DispatchCommitted.from_dict(record)
            except (KeyError, TypeError, TaskControllerValidationError) as exc:
                return None, f"durable DispatchCommitted record is malformed: {exc}"
            return committed, None
        return None, None

    @staticmethod
    def _commit_matches_event(
        committed: DispatchCommitted,
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
        event: MailboxEvent,
    ) -> bool:
        return (
            committed.prepared_id == prepared.prepared_id
            and committed.identity == prepared.identity
            and committed.state_version == prepared.state_version
            and committed.mailbox_ref == prepared.mailbox_ref
            and committed.expected_mailbox_seq == prepared.expected_mailbox_seq
            and committed.mailbox_seq == event.event_seq
            and committed.event_id == event.event_id
            and committed.message_id == prepared.message_id
            and committed.envelope_digest == envelope.digest()
            and committed.event_digest == event.event_digest
            and committed.readback_verified is True
        )

    def _commit_from_existing_event(
        self,
        prepared: DispatchPrepared,
        envelope: V2MailboxEnvelope,
        event: MailboxEvent,
        *,
        reconciled_at: str,
    ) -> DispatchCommitted:
        message_id = event.envelope.to_dict().get("message_id")
        receipt = WriteReceipt(
            mailbox_ref=event.mailbox_ref,
            event_id=event.event_id,
            event_seq=event.event_seq,
            message_id=message_id,
            envelope_digest=event.envelope_digest,
            event_digest=event.event_digest,
            idempotent=True,
        )
        snapshot = self._repository.exact_readback(receipt)
        self._protocol._verify_exact_readback(prepared, envelope, receipt, snapshot)
        committed = DispatchCommitted(
            prepared_id=prepared.prepared_id,
            identity=prepared.identity,
            state_version=prepared.state_version,
            mailbox_ref=prepared.mailbox_ref,
            expected_mailbox_seq=prepared.expected_mailbox_seq,
            mailbox_seq=event.event_seq,
            event_id=event.event_id,
            message_id=message_id,
            envelope_digest=event.envelope_digest,
            event_digest=event.event_digest,
            readback_verified=True,
            committed_id=f"dispatch-committed:{prepared.envelope_digest}",
            committed_at=reconciled_at,
        )
        self._protocol._append_or_readback(self._protocol._committed_event(committed))
        return committed

    @staticmethod
    def _evidence_refs(
        prepared: DispatchPrepared,
        event: MailboxEvent | None,
        committed: DispatchCommitted | None,
    ) -> tuple[str, ...]:
        refs = [prepared.prepared_id, prepared.mailbox_ref]
        if event is not None:
            refs.append(f"{prepared.mailbox_ref}:event-{event.event_id}")
        if committed is not None:
            refs.append(committed.committed_id)
        return tuple(refs)

    def _blocked(
        self,
        prepared: DispatchPrepared,
        state: str,
        reason: str,
        *,
        event: MailboxEvent | None = None,
    ) -> ReconciliationDecision:
        return ReconciliationDecision(
            state=state,
            action=RECONCILIATION_BLOCKED,
            reason=f"{RECONCILIATION_BLOCKED}: {reason}",
            evidence_refs=self._evidence_refs(prepared, event, None),
            committed=None,
            blocked=True,
        )


def snapshot_last_event_seq(events: tuple[MailboxEvent, ...] | list[MailboxEvent]) -> int:
    """Return the append-only mailbox tail sequence without inferring gaps."""

    return events[-1].event_seq if events else -1


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
