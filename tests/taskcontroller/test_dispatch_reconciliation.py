from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.interaction.mailbox_repository import InMemoryMailboxRepository
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.runtime.dispatch_ledger import (
    DISPATCH_COMMITTED,
    DISPATCH_PREPARED,
    RECONCILIATION_BLOCKED,
    RECONCILIATION_CONSUME,
    RECONCILIATION_REPAIR,
    RECONCILIATION_RETRY,
    DispatchPrepared,
    DispatchProtocol,
    DispatchReconciler,
    ReconciliationDecision,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
MAILBOX_REF = "github://owner/repo/issues/208#controller"


def _envelope(
    *,
    message_id: str = "message-dispatch-208",
    idempotency_key: str = "idem-dispatch-208",
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


def _conflicting_envelope(envelope: V2MailboxEnvelope) -> V2MailboxEnvelope:
    payload = envelope.to_dict()
    payload["message_id"] = "message-dispatch-208-conflict"
    payload["attempt"]["attempt_id"] = "attempt-message-dispatch-208-conflict"
    payload["execution_identity"]["attempt_id"] = payload["attempt"]["attempt_id"]
    payload["payload"]["dispatch_test_message"] = "conflicting-payload"
    # Keep the idempotency key and producer namespace: this is a conflicting
    # replay of the same logical write, not an unrelated mailbox event.
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _protocol(
    tmp_path: Path,
    repository: Any | None = None,
) -> tuple[DispatchProtocol, AuditFacade, Any]:
    ledger = AuditFacade(tmp_path / "dispatch-reconciliation-ledger.sqlite3")
    repo = repository or InMemoryMailboxRepository()
    return DispatchProtocol(repository=repo, ledger=ledger), ledger, repo


def _prepare(protocol: DispatchProtocol, envelope: V2MailboxEnvelope) -> DispatchPrepared:
    return protocol.prepare(
        envelope,
        mailbox_ref=MAILBOX_REF,
        expected_mailbox_seq=-1,
        state_version=8,
        lease_generation=1,
        prepared_at="2026-09-11T04:20:00+07:00",
    )


def _reconciler(repository: Any, ledger: AuditFacade) -> DispatchReconciler:
    return DispatchReconciler(repository=repository, ledger=ledger)


def test_prepared_without_mailbox_retries_once_and_commits_without_duplicate_event(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)

    decision = _reconciler(repository, ledger).reconcile(
        prepared,
        envelope,
        reconciled_at="2026-09-11T04:20:01+07:00",
    )

    assert isinstance(decision, ReconciliationDecision)
    assert decision.state == "PREPARED_NO_MAILBOX"
    assert decision.action == RECONCILIATION_RETRY
    assert decision.committed is not None
    assert decision.committed.mailbox_seq == 0
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED,
        DISPATCH_COMMITTED,
    ]

    replay = _reconciler(repository, ledger).reconcile(
        prepared,
        envelope,
        reconciled_at="2026-09-11T04:20:02+07:00",
    )
    assert replay.action == RECONCILIATION_CONSUME
    assert replay.committed == decision.committed
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert len(ledger.events(envelope.run_id)) == 2
    ledger.close()


def test_mailbox_committed_without_ledger_commit_repairs_ledger_only(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    mailbox_receipt = repository.write(
        MAILBOX_REF,
        prepared.expected_mailbox_seq,
        envelope,
        expected_identity=prepared.identity.execution_identity(),
    )
    assert mailbox_receipt.event_seq == 0
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED
    ]

    decision = _reconciler(repository, ledger).reconcile(
        prepared,
        envelope,
        reconciled_at="2026-09-11T04:20:03+07:00",
    )

    assert decision.state == "MAILBOX_COMMITTED_LEDGER_UNCOMMITTED"
    assert decision.action == RECONCILIATION_REPAIR
    assert decision.committed is not None
    assert decision.committed.event_id == mailbox_receipt.event_id
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED,
        DISPATCH_COMMITTED,
    ]
    ledger.close()


def test_exact_mailbox_and_ledger_commit_are_consumed_without_mutation(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    committed = protocol.dispatch(
        prepared,
        envelope,
        committed_at="2026-09-11T04:20:04+07:00",
    )
    before_events = tuple(ledger.events(envelope.run_id))
    before_mailbox = repository.read(MAILBOX_REF)

    decision = _reconciler(repository, ledger).reconcile(
        prepared,
        envelope,
        reconciled_at="2026-09-11T04:20:05+07:00",
    )

    assert decision.state == "DISPATCH_COMMITTED"
    assert decision.action == RECONCILIATION_CONSUME
    assert decision.committed == committed
    assert tuple(ledger.events(envelope.run_id)) == before_events
    assert repository.read(MAILBOX_REF) == before_mailbox
    ledger.close()


def test_same_idempotency_key_with_conflicting_identity_or_digest_blocks_without_advancement(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    conflicting = _conflicting_envelope(envelope)
    repository.write(
        MAILBOX_REF,
        prepared.expected_mailbox_seq,
        conflicting,
        expected_identity=None,
    )

    decision = _reconciler(repository, ledger).reconcile(
        prepared,
        envelope,
        reconciled_at="2026-09-11T04:20:06+07:00",
    )

    assert decision.state == "IDENTITY_OR_DIGEST_CONFLICT"
    assert decision.action == RECONCILIATION_BLOCKED
    assert decision.committed is None
    assert decision.blocked is True
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED
    ]
    ledger.close()


def test_unexpected_successor_interleaving_blocks_instead_of_retrying(
    tmp_path: Path,
) -> None:
    protocol, ledger, repository = _protocol(tmp_path)
    envelope = _envelope()
    prepared = _prepare(protocol, envelope)
    other = _envelope(
        message_id="message-interleaving",
        idempotency_key="idem-interleaving",
        producer="other-controller",
    )
    repository.write(MAILBOX_REF, prepared.expected_mailbox_seq, other)

    decision = _reconciler(repository, ledger).reconcile(
        prepared,
        envelope,
        reconciled_at="2026-09-11T04:20:07+07:00",
    )

    assert decision.action == RECONCILIATION_BLOCKED
    assert decision.state == "IDENTITY_OR_DIGEST_CONFLICT"
    assert len(repository.read(MAILBOX_REF).events) == 1
    assert [event.decision_kind for event in ledger.events(envelope.run_id)] == [
        DISPATCH_PREPARED
    ]
    ledger.close()


@pytest.mark.parametrize(
    "action",
    [RECONCILIATION_RETRY, RECONCILIATION_REPAIR, RECONCILIATION_CONSUME, RECONCILIATION_BLOCKED],
)
def test_reconciliation_decision_exposes_exactly_one_machine_action(action: str) -> None:
    decision = ReconciliationDecision(
        state="TEST",
        action=action,
        reason="bounded test decision",
        evidence_refs=(MAILBOX_REF,),
        committed=None,
        blocked=action == RECONCILIATION_BLOCKED,
    )
    payload = decision.to_dict()
    assert payload["action"] == action
    assert set(payload).issuperset({"state", "action", "reason", "evidence_refs", "blocked"})
    assert action in {
        RECONCILIATION_RETRY,
        RECONCILIATION_REPAIR,
        RECONCILIATION_CONSUME,
        RECONCILIATION_BLOCKED,
    }
