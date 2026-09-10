from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)
from taskcontroller.interaction.mailbox_repository import InMemoryMailboxRepository
from taskcontroller.runtime.dispatch_ledger import (
    DISPATCH_COMMITTED,
    DISPATCH_PREPARED,
    DispatchCommitted,
    DispatchPrepared,
    DispatchProtocol,
)
from taskcontroller.interaction.wakeup_gate import (
    WAKEUP_DUPLICATE,
    WAKEUP_EMITTED,
    WakeupGate,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"


def _envelope(
    *,
    message_id: str = "message-dispatch-207",
    idempotency_key: str = "idem-dispatch-207",
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


def _protocol(tmp_path: Path, repository: Any | None = None) -> tuple[DispatchProtocol, AuditFacade, Any]:
    ledger = AuditFacade(tmp_path / "dispatch-ledger.sqlite3")
    repo = repository or InMemoryMailboxRepository()
    return DispatchProtocol(repository=repo, ledger=ledger), ledger, repo


def _prepare(protocol: DispatchProtocol, envelope: V2MailboxEnvelope) -> DispatchPrepared:
    return protocol.prepare(
        envelope,
        mailbox_ref="github://owner/repo/issues/207#controller",
        expected_mailbox_seq=-1,
        state_version=7,
        lease_generation=1,
        prepared_at="2026-09-11T03:50:00+07:00",
    )


def test_prepare_cas_readback_commit_binds_seq_and_digests_before_pointer_wakeup(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    gate = WakeupGate()

    assert isinstance(prepared, DispatchPrepared)
    assert prepared.expected_mailbox_seq == -1
    assert prepared.envelope_digest == envelope.digest()
    assert prepared.lease_generation == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED
    ]

    committed = protocol.dispatch(prepared, envelope, committed_at="2026-09-11T03:50:01+07:00")

    assert isinstance(committed, DispatchCommitted)
    assert committed.mailbox_seq == 0
    assert committed.mailbox_seq == prepared.expected_mailbox_seq + 1
    assert committed.envelope_digest == prepared.envelope_digest == envelope.digest()
    assert committed.event_digest == repository.read(prepared.mailbox_ref).events[0].event_digest
    assert committed.readback_verified is True
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED,
        DISPATCH_COMMITTED,
    ]
    assert ledger.events(envelope.run_id)[1].after["record"]["mailbox_seq"] == 0
    assert ledger.events(envelope.run_id)[1].after["record"]["event_digest"] == committed.event_digest

    wake = gate.issue(
        committed,
        sender="controller",
        recipient="hermes-cloud",
        updated_at="2026-09-11T03:50:02+07:00",
    )

    assert wake.status == WAKEUP_EMITTED
    assert wake.signal is not None
    assert wake.signal.seq == committed.mailbox_seq + 1
    assert wake.signal.mailbox_ref == committed.mailbox_ref
    assert wake.envelope_digest == committed.envelope_digest
    assert wake.event_digest == committed.event_digest
    assert set(wake.signal.to_dict()) == {
        "protocol",
        "run_id",
        "sender",
        "recipient",
        "mailbox_ref",
        "seq",
        "updated_at",
    }
    ledger.close()


def test_wakeup_gate_rejects_prepared_state_without_emitting_pointer(tmp_path: Path) -> None:
    protocol, ledger, _ = _protocol(tmp_path)
    prepared = _prepare(protocol, _envelope())
    gate = WakeupGate()

    with pytest.raises(TaskControllerValidationError, match="DispatchCommitted"):
        gate.issue(
            prepared,
            sender="controller",
            recipient="hermes-cloud",
            updated_at="2026-09-11T03:50:02+07:00",
        )

    assert [event.decision_kind for event in ledger.events(prepared.run_id)] == [
        DISPATCH_PREPARED
    ]
    ledger.close()


def test_cas_failure_leaves_only_prepared_record_and_blocks_wakeup(tmp_path: Path) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    existing = _envelope(message_id="message-existing", idempotency_key="idem-existing")
    repository.write("github://owner/repo/issues/207#controller", -1, existing)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    with pytest.raises(TaskControllerValidationError) as caught:
        protocol.dispatch(prepared, envelope, committed_at="2026-09-11T03:50:01+07:00")
    assert getattr(caught.value, "code", None) == MailboxV2ErrorCode.INVALID_SEQUENCE

    events = ledger.events(envelope.run_id)
    assert [event.decision_kind for event in events] == [DISPATCH_PREPARED]
    assert len(repository.read(prepared.mailbox_ref).events) == 1
    with pytest.raises(TaskControllerValidationError, match="DispatchCommitted"):
        WakeupGate().issue(
            prepared,
            sender="controller",
            recipient="hermes-cloud",
            updated_at="2026-09-11T03:50:02+07:00",
        )
    ledger.close()


class FailedReadbackRepository(InMemoryMailboxRepository):
    def exact_readback(self, receipt):  # type: ignore[no-untyped-def]
        super().exact_readback(receipt)
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "simulated exact-readback interruption",
        )


def test_exact_readback_failure_leaves_only_prepared_record_and_blocks_wakeup(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path, FailedReadbackRepository())
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    with pytest.raises(MailboxV2ValidationError, match="exact-readback interruption"):
        protocol.dispatch(prepared, envelope, committed_at="2026-09-11T03:50:01+07:00")

    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED
    ]
    assert len(repository.read(prepared.mailbox_ref).events) == 1
    with pytest.raises(TaskControllerValidationError, match="DispatchCommitted"):
        WakeupGate().issue(
            prepared,
            sender="controller",
            recipient="hermes-cloud",
            updated_at="2026-09-11T03:50:02+07:00",
        )
    ledger.close()


def test_replaying_same_prepared_write_is_idempotent_and_emits_one_pointer(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    first = protocol.dispatch(prepared, envelope, committed_at="2026-09-11T03:50:01+07:00")
    second = protocol.dispatch(prepared, envelope, committed_at="2026-09-11T03:50:02+07:00")

    assert second == first
    assert len(repository.read(prepared.mailbox_ref).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED,
        DISPATCH_COMMITTED,
    ]

    gate = WakeupGate()
    first_wake = gate.issue(
        first,
        sender="controller",
        recipient="hermes-cloud",
        updated_at="2026-09-11T03:50:03+07:00",
    )
    second_wake = gate.issue(
        second,
        sender="controller",
        recipient="hermes-cloud",
        updated_at="2026-09-11T03:50:04+07:00",
    )
    assert first_wake.status == WAKEUP_EMITTED
    assert second_wake.status == WAKEUP_DUPLICATE
    assert second_wake.signal is None
    ledger.close()
