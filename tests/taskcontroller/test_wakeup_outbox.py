"""TC-MBX-308: durable WakeupIntent outbox isolation and idempotency."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.controlplane.mailbox_dispatch import (
    MailboxDispatchOutcome,
    dispatch_v2_with_cursor,
)
from taskcontroller.controlplane.wakeup_dispatch import emit_pointer_only_wakeup
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import InMemoryMailboxRepository
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)
from taskcontroller.runtime.dispatch_ledger import DispatchPrepared, DispatchProtocol
from taskcontroller.controlplane.wakeup_outbox import (
    WAKEUP_ATTEMPT_DELIVERED,
    WAKEUP_ATTEMPT_FAILED,
    WAKEUP_INTENT_PENDING,
    WakeupDeliveryAttempt,
    WakeupIntent,
    WakeupOutbox,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
MAILBOX_REF = "github://owner/repo/issues/308#controller"
RECIPIENT = "hermes-mac"


def _envelope(
    *,
    message_id: str = "message-dispatch-308",
    idempotency_key: str = "idem-dispatch-308",
) -> V2MailboxEnvelope:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = copy.deepcopy(fixture["cases"]["execution_request"])
    payload["message_id"] = message_id
    payload["idempotency_key"] = idempotency_key
    payload["attempt"]["attempt_id"] = f"attempt-{message_id}"
    payload["execution_identity"]["attempt_id"] = payload["attempt"]["attempt_id"]
    payload["payload"]["dispatch_test_message"] = message_id
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _bound_dispatch(
    tmp_path: Path,
) -> tuple[
    V2MailboxEnvelope,
    DispatchPrepared,
    MailboxDispatchOutcome,
    Any,
    Any,
]:
    ledger = AuditFacade(tmp_path / "dispatch-ledger.sqlite3")
    repository = InMemoryMailboxRepository()
    protocol = DispatchProtocol(repository=repository, ledger=ledger)
    envelope = _envelope()
    prepared = protocol.prepare(
        envelope,
        mailbox_ref=MAILBOX_REF,
        expected_mailbox_seq=-1,
        state_version=12,
        lease_generation=1,
        prepared_at="2026-09-11T07:00:00+07:00",
    )
    outcome = dispatch_v2_with_cursor(
        protocol,
        prepared,
        envelope,
        committed_at="2026-09-11T07:00:01+07:00",
    )
    emission = emit_pointer_only_wakeup(
        outcome,
        envelope,
        sender="controller",
        recipient=RECIPIENT,
        updated_at="2026-09-11T07:00:02+07:00",
    )
    return envelope, prepared, outcome, emission, (repository, ledger)


def _create_intent(
    outbox: WakeupOutbox,
    outcome: MailboxDispatchOutcome,
    emission: Any,
    *,
    created_at: str = "2026-09-11T07:00:03+07:00",
) -> WakeupIntent:
    return outbox.create_intent(
        outcome,
        emission,
        recipient=RECIPIENT,
        created_at=created_at,
        fallback="mailbox_poll",
        claim_ttl_seconds=300,
    )


def test_intent_is_created_only_from_verified_commit_and_round_trips_without_payload(
    tmp_path: Path,
) -> None:
    envelope, prepared, outcome, emission, (repository, ledger) = _bound_dispatch(tmp_path)
    outbox = WakeupOutbox(tmp_path / "wakeup-outbox.sqlite3")

    intent = _create_intent(outbox, outcome, emission)

    assert isinstance(intent, WakeupIntent)
    assert intent.state == WAKEUP_INTENT_PENDING
    assert intent.mailbox_ref == MAILBOX_REF
    assert intent.mailbox_seq == outcome.committed.mailbox_seq
    assert intent.event_id == outcome.committed.event_id
    assert intent.event_digest == outcome.committed.event_digest
    assert intent.envelope_digest == envelope.digest()
    assert intent.idempotency_key == envelope.idempotency_key
    assert intent.recipient == RECIPIENT
    assert intent.attempt_count == 0
    assert intent.fallback == "mailbox_poll"
    assert intent.claim_ttl_seconds == 300
    assert "payload" not in intent.to_dict()

    outbox.close()
    reopened = WakeupOutbox(tmp_path / "wakeup-outbox.sqlite3")
    assert reopened.get_intent(intent.intent_id) == intent
    assert WakeupIntent.from_dict(intent.to_dict()) == intent
    assert len(reopened.list_intents()) == 1
    assert len(repository.read(MAILBOX_REF).events) == 1
    reopened.close()
    ledger.close()


def test_duplicate_intent_is_one_logical_wake_and_conflicting_digest_is_rejected(
    tmp_path: Path,
) -> None:
    _, _, outcome, emission, (_, ledger) = _bound_dispatch(tmp_path)
    outbox = WakeupOutbox(tmp_path / "wakeup-outbox.sqlite3")
    first = _create_intent(outbox, outcome, emission)

    duplicate = _create_intent(
        outbox,
        outcome,
        emission,
        created_at="2026-09-11T07:00:04+07:00",
    )
    assert duplicate == first
    assert len(outbox.list_intents()) == 1

    conflicting_digest = "sha256:" + ("f" * 64)
    conflicting_committed = replace(
        outcome.committed,
        event_digest=conflicting_digest,
        committed_id="dispatch-committed:conflicting-308",
    )
    conflicting_outcome = MailboxDispatchOutcome(
        committed=conflicting_committed,
        cursor=replace(outcome.cursor, last_event_digest=conflicting_digest),
    )
    conflicting_emission = replace(
        emission,
        decision=replace(
            emission.decision,
            dispatch_id=conflicting_committed.committed_id,
            event_digest=conflicting_digest,
        ),
    )

    with pytest.raises(MailboxV2ValidationError) as exc_info:
        _create_intent(outbox, conflicting_outcome, conflicting_emission)
    assert exc_info.value.code == MailboxV2ErrorCode.DIGEST_MISMATCH
    assert len(outbox.list_intents()) == 1
    outbox.close()
    ledger.close()


def test_delivery_attempts_are_separate_and_retry_keeps_mailbox_event_immutable(
    tmp_path: Path,
) -> None:
    envelope, _, outcome, emission, (repository, ledger) = _bound_dispatch(tmp_path)
    outbox = WakeupOutbox(tmp_path / "wakeup-outbox.sqlite3")
    intent = _create_intent(outbox, outcome, emission)
    before_snapshot = repository.read(MAILBOX_REF)
    before_cursor = repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    )

    first_attempt = outbox.record_delivery_attempt(
        intent.intent_id,
        attempt_id="wakeup-delivery-attempt-1",
        attempt_number=1,
        state=WAKEUP_ATTEMPT_FAILED,
        attempted_at="2026-09-11T07:00:04+07:00",
        retry_at="2026-09-11T07:01:04+07:00",
        error_code="TRANSPORT_UNAVAILABLE",
    )
    assert isinstance(first_attempt, WakeupDeliveryAttempt)
    assert first_attempt.attempt_number == 1
    duplicate_attempt = outbox.record_delivery_attempt(
        intent.intent_id,
        attempt_id="wakeup-delivery-attempt-1",
        attempt_number=1,
        state=WAKEUP_ATTEMPT_FAILED,
        attempted_at="2026-09-11T07:00:04+07:00",
        retry_at="2026-09-11T07:01:04+07:00",
        error_code="TRANSPORT_UNAVAILABLE",
    )
    assert duplicate_attempt == first_attempt
    assert len(outbox.list_attempts(intent.intent_id)) == 1
    assert outbox.get_intent(intent.intent_id).attempt_count == 1

    retry = outbox.prepare_retry(
        intent.intent_id,
        retry_at="2026-09-11T07:01:04+07:00",
    )
    assert retry.intent_id == intent.intent_id
    assert retry.mailbox_ref == intent.mailbox_ref
    assert retry.mailbox_seq == intent.mailbox_seq
    assert retry.event_id == intent.event_id
    assert retry.event_digest == intent.event_digest
    assert retry.envelope_digest == intent.envelope_digest
    assert retry.idempotency_key == intent.idempotency_key
    assert retry.attempt_count == 1

    second_attempt = outbox.record_delivery_attempt(
        retry.intent_id,
        attempt_id="wakeup-delivery-attempt-2",
        attempt_number=2,
        state=WAKEUP_ATTEMPT_DELIVERED,
        attempted_at="2026-09-11T07:01:05+07:00",
    )
    assert second_attempt.attempt_number == 2
    assert [attempt.attempt_number for attempt in outbox.list_attempts(intent.intent_id)] == [1, 2]
    assert outbox.get_intent(intent.intent_id).attempt_count == 2

    # The retry path has no repository handle and therefore cannot rewrite the
    # canonical request/event. The single committed event remains exact.
    after_snapshot = repository.read(MAILBOX_REF)
    after_cursor = repository.read_cursor(
        MAILBOX_REF,
        envelope.run_id,
        envelope.node_id,
        envelope.producer_namespace,
    )
    assert after_snapshot == before_snapshot
    assert after_cursor == before_cursor
    assert len(after_snapshot.events) == 1
    assert after_snapshot.events[0].event_digest == intent.event_digest
    assert after_snapshot.events[0].envelope_digest == intent.envelope_digest
    assert after_snapshot.events[0].envelope.to_dict()["idempotency_key"] == intent.idempotency_key
    outbox.close()
    ledger.close()


def test_unverified_or_mismatched_pointer_evidence_fails_closed(tmp_path: Path) -> None:
    _, prepared, outcome, emission, (_, ledger) = _bound_dispatch(tmp_path)
    outbox = WakeupOutbox(tmp_path / "wakeup-outbox.sqlite3")

    with pytest.raises(TaskControllerValidationError, match="MailboxDispatchOutcome"):
        outbox.create_intent(
            prepared,
            emission,
            recipient=RECIPIENT,
            created_at="2026-09-11T07:00:03+07:00",
        )

    mismatched_emission = replace(
        emission,
        decision=replace(emission.decision, mailbox_seq=emission.decision.mailbox_seq + 1),
    )
    with pytest.raises(MailboxV2ValidationError) as exc_info:
        _create_intent(outbox, outcome, mismatched_emission)
    assert exc_info.value.code == MailboxV2ErrorCode.CONTRACT_MISMATCH
    assert outbox.list_intents() == ()
    outbox.close()
    ledger.close()
