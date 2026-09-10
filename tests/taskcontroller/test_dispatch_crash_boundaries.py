from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.interaction.mailbox_repository import (
    InMemoryMailboxRepository,
    MailboxActorCursor,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.interaction.wakeup_gate import (
    WAKEUP_DUPLICATE,
    WAKEUP_EMITTED,
    WakeupGate,
)
from taskcontroller.runtime.dispatch_ledger import (
    DISPATCH_COMMITTED,
    DISPATCH_PREPARED,
    RECONCILIATION_CONSUME,
    RECONCILIATION_REPAIR,
    RECONCILIATION_RETRY,
    DispatchPrepared,
    DispatchProtocol,
    DispatchReconciler,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
MAILBOX_REF = "github://owner/repo/issues/209#controller"


class CrashInjected(RuntimeError):
    """Synthetic process loss at one named persistence boundary."""


class CrashBeforeMailboxAppend(DispatchProtocol):
    """Crash after durable DispatchPrepared and before the mailbox CAS call."""

    def dispatch(self, prepared, envelope, *, committed_at):  # type: ignore[no-untyped-def]
        raise CrashInjected("crash after DispatchPrepared before mailbox append")


class CrashAfterMailboxWrite(InMemoryMailboxRepository):
    """Persist the mailbox event, then lose the process before exact readback."""

    def __init__(self) -> None:
        super().__init__()
        self.write_calls = 0

    def write(self, mailbox_ref, expected_seq, envelope, *, expected_identity=None):  # type: ignore[no-untyped-def]
        receipt = super().write(
            mailbox_ref,
            expected_seq,
            envelope,
            expected_identity=expected_identity,
        )
        self.write_calls += 1
        if self.write_calls == 1:
            raise CrashInjected("crash after mailbox append before exact readback")
        return receipt


class CrashAfterExactReadback(InMemoryMailboxRepository):
    """Complete exact readback, then lose the process before ledger commit."""

    def __init__(self) -> None:
        super().__init__()
        self.readback_calls = 0

    def exact_readback(self, receipt):  # type: ignore[no-untyped-def]
        snapshot = super().exact_readback(receipt)
        self.readback_calls += 1
        if self.readback_calls == 1:
            raise CrashInjected("crash after exact readback before ledger commit")
        return snapshot


class CrashAfterLedgerCommit:
    """Persist DispatchCommitted, then lose the process before pointer wakeup."""

    def __init__(self, ledger: AuditFacade) -> None:
        self._ledger = ledger
        self.crashed = False

    def record(self, run_id: str, event):  # type: ignore[no-untyped-def]
        result = self._ledger.record(run_id, event)
        if event.decision_kind == DISPATCH_COMMITTED and not self.crashed:
            self.crashed = True
            raise CrashInjected("crash after durable ledger commit before wakeup")
        return result

    def events(self, run_id: str):  # type: ignore[no-untyped-def]
        return self._ledger.events(run_id)

    def close(self) -> None:
        self._ledger.close()


def _envelope(
    *,
    message_id: str = "message-dispatch-209",
    idempotency_key: str = "idem-dispatch-209",
    producer: str = "controller",
) -> V2MailboxEnvelope:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = copy.deepcopy(fixture["cases"]["execution_request"])
    payload["message_id"] = message_id
    payload["idempotency_key"] = idempotency_key
    payload["producer"] = {
        "namespace": producer,
        "actor_id": f"{producer}-actor",
        "role": "controller",
    }
    payload["attempt"]["attempt_id"] = f"attempt-{message_id}"
    payload["execution_identity"]["attempt_id"] = payload["attempt"]["attempt_id"]
    payload["payload"]["dispatch_test_message"] = message_id
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _ledger(tmp_path: Path) -> tuple[AuditFacade, Path]:
    path = tmp_path / "dispatch-crash-boundary-ledger.sqlite3"
    return AuditFacade(path), path


def _prepare(protocol: DispatchProtocol, envelope: V2MailboxEnvelope) -> DispatchPrepared:
    return protocol.prepare(
        envelope,
        mailbox_ref=MAILBOX_REF,
        expected_mailbox_seq=-1,
        state_version=9,
        lease_generation=1,
        prepared_at="2026-09-11T05:20:00+07:00",
    )


def _reconcile_after_restart(
    repository: Any,
    ledger_path: Path,
    prepared: DispatchPrepared,
    envelope: V2MailboxEnvelope,
    *,
    reconciled_at: str,
):
    ledger = AuditFacade(ledger_path)
    decision = DispatchReconciler(repository=repository, ledger=ledger).reconcile(
        prepared,
        envelope,
        reconciled_at=reconciled_at,
    )
    return decision, ledger


def _assert_one_mailbox_event_and_commit(
    repository: Any,
    ledger: AuditFacade,
    envelope: V2MailboxEnvelope,
    expected_event_kind: str = DISPATCH_COMMITTED,
) -> None:
    mailbox_events = repository.read(MAILBOX_REF).events
    assert len(mailbox_events) == 1
    assert mailbox_events[0].envelope_digest == envelope.digest()
    ledger_events = ledger.events(envelope.run_id)
    assert [event.decision_kind for event in ledger_events] == [
        DISPATCH_PREPARED,
        expected_event_kind,
    ]
    assert ledger_events[1].after["record"]["event_digest"] == mailbox_events[0].event_digest


def test_crash_after_prepare_retries_once_and_replays_as_consume(tmp_path: Path) -> None:
    ledger, ledger_path = _ledger(tmp_path)
    repository = InMemoryMailboxRepository()
    envelope = _envelope()
    protocol = DispatchProtocol(repository=repository, ledger=ledger)
    prepared = _prepare(protocol, envelope)

    with pytest.raises(CrashInjected, match="before mailbox append"):
        CrashBeforeMailboxAppend(repository=repository, ledger=ledger).dispatch(
            prepared,
            envelope,
            committed_at="2026-09-11T05:20:01+07:00",
        )
    assert repository.read(MAILBOX_REF).events == ()
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [DISPATCH_PREPARED]
    ledger.close()

    decision, restarted_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:20:02+07:00",
    )
    assert decision.action == RECONCILIATION_RETRY
    assert decision.committed is not None
    _assert_one_mailbox_event_and_commit(repository, restarted_ledger, envelope)
    restarted_ledger.close()

    replay, replay_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:20:03+07:00",
    )
    assert replay.action == RECONCILIATION_CONSUME
    assert replay.committed == decision.committed
    _assert_one_mailbox_event_and_commit(repository, replay_ledger, envelope)
    replay_ledger.close()


def test_crash_after_mailbox_append_repairs_ledger_without_duplicate_event(
    tmp_path: Path,
) -> None:
    repository = CrashAfterMailboxWrite()
    ledger, ledger_path = _ledger(tmp_path)
    envelope = _envelope()
    prepared = _prepare(DispatchProtocol(repository=repository, ledger=ledger), envelope)

    with pytest.raises(CrashInjected, match="mailbox append"):
        DispatchProtocol(repository=repository, ledger=ledger).dispatch(
            prepared,
            envelope,
            committed_at="2026-09-11T05:21:01+07:00",
        )
    assert repository.write_calls == 1
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [DISPATCH_PREPARED]
    ledger.close()

    decision, restarted_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:21:02+07:00",
    )
    assert decision.action == RECONCILIATION_REPAIR
    assert decision.committed is not None
    assert repository.write_calls == 1
    _assert_one_mailbox_event_and_commit(repository, restarted_ledger, envelope)
    restarted_ledger.close()

    replay, replay_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:21:03+07:00",
    )
    assert replay.action == RECONCILIATION_CONSUME
    assert replay.committed == decision.committed
    assert repository.write_calls == 1
    _assert_one_mailbox_event_and_commit(repository, replay_ledger, envelope)
    replay_ledger.close()


def test_crash_after_exact_readback_repairs_ledger_without_losing_result(
    tmp_path: Path,
) -> None:
    repository = CrashAfterExactReadback()
    ledger, ledger_path = _ledger(tmp_path)
    envelope = _envelope()
    prepared = _prepare(DispatchProtocol(repository=repository, ledger=ledger), envelope)

    with pytest.raises(CrashInjected, match="exact readback"):
        DispatchProtocol(repository=repository, ledger=ledger).dispatch(
            prepared,
            envelope,
            committed_at="2026-09-11T05:22:01+07:00",
        )
    assert repository.readback_calls == 1
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [DISPATCH_PREPARED]
    ledger.close()

    decision, restarted_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:22:02+07:00",
    )
    assert decision.action == RECONCILIATION_REPAIR
    assert decision.committed is not None
    assert repository.readback_calls == 2
    _assert_one_mailbox_event_and_commit(repository, restarted_ledger, envelope)
    restarted_ledger.close()

    replay, replay_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:22:03+07:00",
    )
    assert replay.action == RECONCILIATION_CONSUME
    assert replay.committed == decision.committed
    assert repository.readback_calls == 2
    _assert_one_mailbox_event_and_commit(repository, replay_ledger, envelope)
    replay_ledger.close()


def test_crash_after_ledger_commit_consumes_and_wakeup_is_one_pointer(
    tmp_path: Path,
) -> None:
    base_ledger, ledger_path = _ledger(tmp_path)
    repository = InMemoryMailboxRepository()
    crash_ledger = CrashAfterLedgerCommit(base_ledger)
    envelope = _envelope()
    protocol = DispatchProtocol(repository=repository, ledger=crash_ledger)
    prepared = _prepare(protocol, envelope)

    with pytest.raises(CrashInjected, match="ledger commit"):
        protocol.dispatch(
            prepared,
            envelope,
            committed_at="2026-09-11T05:23:01+07:00",
        )
    assert crash_ledger.crashed is True
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in crash_ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED,
        DISPATCH_COMMITTED,
    ]
    crash_ledger.close()

    decision, restarted_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:23:02+07:00",
    )
    assert decision.action == RECONCILIATION_CONSUME
    assert decision.committed is not None
    _assert_one_mailbox_event_and_commit(repository, restarted_ledger, envelope)

    gate = WakeupGate()
    first = gate.issue(
        decision.committed,
        sender="controller",
        recipient="hermes-cloud",
        updated_at="2026-09-11T05:23:03+07:00",
    )
    second = gate.issue(
        decision.committed,
        sender="controller",
        recipient="hermes-cloud",
        updated_at="2026-09-11T05:23:04+07:00",
    )
    assert first.status == WAKEUP_EMITTED
    assert second.status == WAKEUP_DUPLICATE
    assert second.signal is None
    restarted_ledger.close()


def test_fresh_repair_and_replay_are_byte_equivalent(tmp_path: Path) -> None:
    ledger, ledger_path = _ledger(tmp_path)
    repository = InMemoryMailboxRepository()
    envelope = _envelope()
    prepared = _prepare(DispatchProtocol(repository=repository, ledger=ledger), envelope)
    repository.write(
        MAILBOX_REF,
        prepared.expected_mailbox_seq,
        envelope,
        expected_identity=prepared.identity.execution_identity(),
    )
    ledger.close()

    repaired, repaired_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:24:01+07:00",
    )
    assert repaired.action == RECONCILIATION_REPAIR
    mailbox_bytes = repository.read(MAILBOX_REF).to_dict()
    ledger_bytes = [event.to_dict() for event in repaired_ledger.events(envelope.run_id)]
    repaired_ledger.close()

    replayed, replay_ledger = _reconcile_after_restart(
        repository,
        ledger_path,
        prepared,
        envelope,
        reconciled_at="2026-09-11T05:24:02+07:00",
    )
    assert replayed.action == RECONCILIATION_CONSUME
    assert replayed.committed == repaired.committed
    assert repository.read(MAILBOX_REF).to_dict() == mailbox_bytes
    assert [event.to_dict() for event in replay_ledger.events(envelope.run_id)] == ledger_bytes
    replay_ledger.close()


def test_cursor_crash_before_ack_replays_once_then_ack_is_durable(tmp_path: Path) -> None:
    ledger, ledger_path = _ledger(tmp_path)
    repository = InMemoryMailboxRepository()
    envelope = _envelope()
    protocol = DispatchProtocol(repository=repository, ledger=ledger)
    prepared = _prepare(protocol, envelope)
    committed = protocol.dispatch(
        prepared,
        envelope,
        committed_at="2026-09-11T05:25:01+07:00",
    )
    event = repository.read(MAILBOX_REF).events[0]
    cursor = MailboxActorCursor.initial(
        MAILBOX_REF,
        run_id=envelope.run_id,
        node_id=envelope.node_id,
        actor_namespace=envelope.producer_namespace,
    )

    before_ack = repository.scan_after_cursor(cursor)
    assert before_ack == (event,)
    # Crash before acknowledgement: a fresh process has the same durable initial cursor.
    restarted_cursor = MailboxActorCursor.from_dict(
        json.loads(json.dumps(cursor.to_dict(), sort_keys=True))
    )
    replay = repository.scan_after_cursor(restarted_cursor)
    assert replay == (event,)
    processed_keys = [item.idempotency_key for item in replay]
    advanced = restarted_cursor.observe(replay[0])
    acknowledged = repository.acknowledge_cursor(advanced)
    assert processed_keys == [envelope.idempotency_key]

    # Crash after acknowledgement: serialized/reloaded cursor consumes nothing and
    # preserves the exact committed mailbox evidence.
    durable_cursor = MailboxActorCursor.from_dict(
        json.loads(json.dumps(acknowledged.to_dict(), sort_keys=True))
    )
    assert repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    ) == acknowledged
    assert repository.scan_after_cursor(durable_cursor) == ()
    assert repository.acknowledge_cursor(durable_cursor) == durable_cursor
    assert event.event_digest == committed.event_digest
    ledger.close()
