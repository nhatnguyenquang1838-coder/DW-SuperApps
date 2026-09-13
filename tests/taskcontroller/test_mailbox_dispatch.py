"""TC-MBX-303: verified v2 mailbox dispatch plus durable cursor update."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import (
    InMemoryMailboxRepository,
    MailboxActorCursor,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)
from taskcontroller.interaction.wakeup_gate import WakeupGate
from taskcontroller.runtime.dispatch_ledger import DispatchPrepared, DispatchProtocol

from taskcontroller.controlplane.mailbox_dispatch import (
    MailboxDispatchOutcome,
    dispatch_v2_with_cursor,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
MAILBOX_REF = "github://owner/repo/issues/303#controller"


def _envelope(
    *,
    message_id: str = "message-dispatch-303",
    idempotency_key: str = "idem-dispatch-303",
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


def _protocol(
    tmp_path: Path,
    repository: Any | None = None,
) -> tuple[DispatchProtocol, AuditFacade, InMemoryMailboxRepository]:
    ledger = AuditFacade(tmp_path / "dispatch-ledger.sqlite3")
    repo = repository or InMemoryMailboxRepository()
    return DispatchProtocol(repository=repo, ledger=ledger), ledger, repo


def _prepare(protocol: DispatchProtocol, envelope: V2MailboxEnvelope) -> DispatchPrepared:
    return protocol.prepare(
        envelope,
        mailbox_ref=MAILBOX_REF,
        expected_mailbox_seq=-1,
        state_version=9,
        lease_generation=1,
        prepared_at="2026-09-11T06:00:00+07:00",
    )


class RecordingRepository(InMemoryMailboxRepository):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def write(self, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        self.calls.append("write")
        return super().write(*args, **kwargs)

    def exact_readback(self, receipt):  # type: ignore[no-untyped-def]
        self.calls.append("exact_readback")
        return super().exact_readback(receipt)

    def read_cursor(self, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        self.calls.append("read_cursor")
        return super().read_cursor(*args, **kwargs)

    def acknowledge_cursor(self, cursor):  # type: ignore[no-untyped-def]
        self.calls.append("acknowledge_cursor")
        return super().acknowledge_cursor(cursor)


class FailedReadbackRepository(RecordingRepository):
    def exact_readback(self, receipt):  # type: ignore[no-untyped-def]
        super().exact_readback(receipt)
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "simulated exact-readback interruption",
        )


class FailedCursorRepository(RecordingRepository):
    def acknowledge_cursor(self, cursor):  # type: ignore[no-untyped-def]
        self.calls.append("acknowledge_cursor")
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "simulated cursor acknowledgement interruption",
        )


class MissingEventReadbackRepository(RecordingRepository):
    def __init__(self) -> None:
        super().__init__()
        self._readback_calls = 0

    def exact_readback(self, receipt):  # type: ignore[no-untyped-def]
        snapshot = super().exact_readback(receipt)
        self._readback_calls += 1
        if self._readback_calls == 1:
            return snapshot
        return replace(
            snapshot,
            events=(),
            last_event_seq=-1,
            accepted_state={
                "accepted_event_ids": [],
                "last_event_digest": None,
                "last_event_seq": -1,
                "producer_sequences": {},
            },
            producer_cursors={},
        )


def test_dispatch_records_verified_seq_digest_then_advances_durable_cursor(
    tmp_path: Path,
) -> None:
    repository = RecordingRepository()
    protocol, ledger, _ = _protocol(tmp_path, repository)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    outcome = dispatch_v2_with_cursor(
        protocol,
        prepared,
        envelope,
        committed_at="2026-09-11T06:00:01+07:00",
    )

    assert isinstance(outcome, MailboxDispatchOutcome)
    assert outcome.committed.mailbox_seq == 0
    assert outcome.committed.envelope_digest == envelope.digest()
    assert outcome.committed.event_digest == outcome.cursor.last_event_digest
    assert outcome.cursor.last_event_seq == outcome.committed.mailbox_seq
    assert outcome.cursor.last_logical_seq == envelope.seq
    assert repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    ) == outcome.cursor
    assert repository.calls.index("write") < repository.calls.index("exact_readback")
    assert repository.calls.index("exact_readback") < repository.calls.index("read_cursor")
    assert repository.calls.index("read_cursor") < repository.calls.index("acknowledge_cursor")
    assert ledger.events(envelope.run_id)[-1].after["record"]["mailbox_seq"] == 0
    ledger.close()


def test_replayed_dispatch_is_idempotent_and_does_not_append_or_reack_different_state(
    tmp_path: Path,
) -> None:
    repository = InMemoryMailboxRepository()
    protocol, ledger, _ = _protocol(tmp_path, repository)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    first = dispatch_v2_with_cursor(
        protocol,
        prepared,
        envelope,
        committed_at="2026-09-11T06:01:01+07:00",
    )

    restarted_protocol = DispatchProtocol(repository=repository, ledger=ledger)
    restarted_prepared = _prepare(restarted_protocol, envelope)
    second = dispatch_v2_with_cursor(
        restarted_protocol,
        restarted_prepared,
        envelope,
        committed_at="2026-09-11T06:01:02+07:00",
    )

    assert second == first
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        "DISPATCH_PREPARED",
        "DISPATCH_COMMITTED",
    ]
    assert repository.scan_after_cursor(second.cursor) == ()
    ledger.close()


def test_failed_exact_readback_cannot_advance_cursor_or_issue_wakeup(
    tmp_path: Path,
) -> None:
    repository = FailedReadbackRepository()
    protocol, ledger, _ = _protocol(tmp_path, repository)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    with pytest.raises(MailboxV2ValidationError, match="exact-readback interruption"):
        dispatch_v2_with_cursor(
            protocol,
            prepared,
            envelope,
            committed_at="2026-09-11T06:02:01+07:00",
        )

    cursor = repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    )
    assert cursor == MailboxActorCursor.initial(
        MAILBOX_REF,
        run_id=envelope.run_id,
        node_id=envelope.node_id,
        actor_namespace=envelope.producer_namespace,
    )
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        "DISPATCH_PREPARED"
    ]
    with pytest.raises(TaskControllerValidationError, match="DispatchCommitted"):
        WakeupGate().issue(
            prepared,
            sender="controller",
            recipient="hermes-mac",
            updated_at="2026-09-11T06:02:02+07:00",
        )
    ledger.close()


def test_missing_exact_readback_event_blocks_cursor_update_and_wakeup(
    tmp_path: Path,
) -> None:
    repository = MissingEventReadbackRepository()
    protocol, ledger, _ = _protocol(tmp_path, repository)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    with pytest.raises(MailboxV2ValidationError, match="omitted"):
        dispatch_v2_with_cursor(
            protocol,
            prepared,
            envelope,
            committed_at="2026-09-11T06:03:01+07:00",
        )

    assert repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    ).last_event_seq == -1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        "DISPATCH_PREPARED",
        "DISPATCH_COMMITTED",
    ]
    with pytest.raises(TaskControllerValidationError, match="DispatchCommitted"):
        WakeupGate().issue(
            prepared,
            sender="controller",
            recipient="hermes-mac",
            updated_at="2026-09-11T06:03:02+07:00",
        )
    ledger.close()


def test_cursor_ack_failure_leaves_committed_evidence_but_no_ready_outcome(
    tmp_path: Path,
) -> None:
    repository = FailedCursorRepository()
    protocol, ledger, _ = _protocol(tmp_path, repository)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    with pytest.raises(MailboxV2ValidationError, match="cursor acknowledgement interruption"):
        dispatch_v2_with_cursor(
            protocol,
            prepared,
            envelope,
            committed_at="2026-09-11T06:04:01+07:00",
        )

    assert repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    ).last_event_seq == -1
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        "DISPATCH_PREPARED",
        "DISPATCH_COMMITTED",
    ]
    ledger.close()
