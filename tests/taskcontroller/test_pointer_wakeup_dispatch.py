"""TC-MBX-304: pointer-only wakeup emission over verified mailbox evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import InMemoryMailboxRepository
from taskcontroller.interaction.mailbox_v2 import (
    V2MailboxEnvelope,
    canonical_digest,
)
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.interaction.wakeup_gate import (
    WAKEUP_DUPLICATE,
    WAKEUP_EMITTED,
    WakeupGate,
)
from taskcontroller.runtime.dispatch_ledger import (
    DispatchPrepared,
    DispatchProtocol,
)
from taskcontroller.controlplane.mailbox_dispatch import (
    MailboxDispatchOutcome,
    dispatch_v2_with_cursor,
)

from taskcontroller.controlplane.wakeup_dispatch import (
    PointerWakeupEmission,
    WAKEUP_PROJECTION_BLOCKED,
    WAKEUP_PROJECTION_DELIVERED,
    WAKEUP_PROJECTION_PENDING,
    WAKEUP_PROJECTION_RETRYING,
    project_wakeup_delivery,
    emit_pointer_only_wakeup,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
MAILBOX_REF = "github://owner/repo/issues/304#controller"


def _envelope(**changes: Any) -> V2MailboxEnvelope:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = copy.deepcopy(fixture["cases"]["execution_request"])
    payload["message_id"] = "message-dispatch-304"
    payload["idempotency_key"] = "idem-dispatch-304"
    payload["producer"] = {
        "namespace": "controller",
        "actor_id": "controller-304",
        "role": "controller",
    }
    payload["attempt"]["attempt_id"] = "attempt-message-dispatch-304"
    payload["execution_identity"]["attempt_id"] = payload["attempt"]["attempt_id"]
    payload["payload"]["dispatch_test_message"] = "message-dispatch-304"
    payload.update(changes)
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _ready(tmp_path: Path) -> tuple[
    DispatchProtocol,
    AuditFacade,
    InMemoryMailboxRepository,
    V2MailboxEnvelope,
    DispatchPrepared,
    MailboxDispatchOutcome,
]:
    ledger = AuditFacade(tmp_path / "dispatch-ledger.sqlite3")
    repository = InMemoryMailboxRepository()
    protocol = DispatchProtocol(repository=repository, ledger=ledger)
    envelope = _envelope()
    prepared = protocol.prepare(
        envelope,
        mailbox_ref=MAILBOX_REF,
        expected_mailbox_seq=-1,
        state_version=7,
        lease_generation=1,
        prepared_at="2026-09-11T06:30:00+07:00",
    )
    outcome = dispatch_v2_with_cursor(
        protocol,
        prepared,
        envelope,
        committed_at="2026-09-11T06:30:01+07:00",
    )
    return protocol, ledger, repository, envelope, prepared, outcome


def _emit(
    outcome: MailboxDispatchOutcome,
    envelope: V2MailboxEnvelope,
    *,
    gate: WakeupGate | None = None,
) -> PointerWakeupEmission:
    return emit_pointer_only_wakeup(
        outcome,
        envelope,
        sender="controller",
        recipient="hermes-mac",
        updated_at="2026-09-11T06:30:02+07:00",
        gate=gate,
    )


def test_emission_contains_pointer_and_bounded_human_projection(tmp_path: Path) -> None:
    _, ledger, _, envelope, _, outcome = _ready(tmp_path)

    emission = _emit(outcome, envelope)
    assert emission.decision.status == WAKEUP_EMITTED
    payload = emission.to_notification_dict()
    assert payload is not None
    assert set(payload) == {
        "protocol",
        "run_id",
        "sender",
        "recipient",
        "mailbox_ref",
        "seq",
        "updated_at",
        "human_projection",
    }
    assert payload["protocol"] == "dw.taskcontroller.wakeup/v1"
    assert payload["run_id"] == envelope.run_id
    assert payload["recipient"] == "hermes-mac"
    assert payload["mailbox_ref"] == MAILBOX_REF
    assert payload["seq"] == outcome.committed.mailbox_seq + 1
    assert payload["human_projection"]["kind"] == "SUBTASK_STARTED"
    assert payload["human_projection"]["status"] == "DISPATCHED"
    assert payload["human_projection"]["evidence_refs"] == [MAILBOX_REF]

    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "request",
        "objective",
        "acceptance_criteria",
        "scope",
        "payload",
        "code",
        "context",
    ):
        assert forbidden not in serialized
    assert "Run one bounded mailbox v2 contract check." not in serialized
    ledger.close()


def test_notification_pointer_round_trips_as_existing_v1_signal(tmp_path: Path) -> None:
    _, ledger, _, envelope, _, outcome = _ready(tmp_path)

    payload = _emit(outcome, envelope).to_notification_dict()
    assert payload is not None
    signal = WakeupSignal.from_dict(
        {key: value for key, value in payload.items() if key != "human_projection"}
    )

    assert signal.run_id == envelope.run_id
    assert signal.recipient == "hermes-mac"
    assert signal.mailbox_ref == MAILBOX_REF
    assert signal.seq == outcome.committed.mailbox_seq + 1
    ledger.close()


def test_duplicate_emission_is_idempotent_and_has_no_second_notification(
    tmp_path: Path,
) -> None:
    _, ledger, _, envelope, _, outcome = _ready(tmp_path)
    gate = WakeupGate()

    first = _emit(outcome, envelope, gate=gate)
    second = _emit(outcome, envelope, gate=gate)

    assert first.decision.status == WAKEUP_EMITTED
    assert first.to_notification_dict() is not None
    assert second.decision.status == WAKEUP_DUPLICATE
    assert second.decision.signal is None
    assert second.human_projection is None
    assert second.to_notification_dict() is None
    ledger.close()


def test_prepared_or_wrong_recipient_evidence_fails_closed_without_emission(
    tmp_path: Path,
) -> None:
    _, ledger, _, envelope, prepared, outcome = _ready(tmp_path)

    with pytest.raises(TaskControllerValidationError, match="MailboxDispatchOutcome"):
        emit_pointer_only_wakeup(
            prepared,
            envelope,
            sender="controller",
            recipient="hermes-mac",
            updated_at="2026-09-11T06:30:02+07:00",
        )

    with pytest.raises(TaskControllerValidationError, match="recipient"):
        emit_pointer_only_wakeup(
            outcome,
            envelope,
            sender="controller",
            recipient="hermes-cloud",
            updated_at="2026-09-11T06:30:02+07:00",
        )
    ledger.close()


def test_pointer_reconstructs_canonical_mailbox_without_human_history(
    tmp_path: Path,
) -> None:
    _, ledger, repository, envelope, _, outcome = _ready(tmp_path)

    payload = _emit(outcome, envelope).to_notification_dict()
    assert payload is not None
    pointer_only = {
        key: payload[key]
        for key in ("protocol", "run_id", "recipient", "mailbox_ref", "seq")
    }
    assert "human_projection" not in pointer_only

    snapshot = repository.read(pointer_only["mailbox_ref"])
    event_seq = pointer_only["seq"] - 1
    event = next(event for event in snapshot.events if event.event_seq == event_seq)

    assert event.envelope == envelope
    assert event.envelope.run_id == pointer_only["run_id"]
    assert event.envelope.to_dict()["recipient"]["agent_instance"] == pointer_only["recipient"]
    assert event.event_seq == outcome.committed.mailbox_seq
    ledger.close()


def _projection_ready(tmp_path: Path) -> tuple[Any, Any, Any, Any, Any]:
    from taskcontroller.controlplane.wakeup_outbox import WakeupOutbox

    _, ledger, repository, envelope, _, outcome = _ready(tmp_path)
    emission = _emit(outcome, envelope)
    outbox = WakeupOutbox(tmp_path / "wakeup-projection.sqlite3")
    intent = outbox.create_intent(
        outcome,
        emission,
        recipient="hermes-mac",
        created_at="2026-09-11T06:30:03+07:00",
        fallback="mailbox_poll",
        claim_ttl_seconds=300,
    )
    return outbox, ledger, repository, envelope, intent


def test_operator_projection_distinguishes_persisted_request_from_untriggered_executor(
    tmp_path: Path,
) -> None:
    outbox, ledger, repository, envelope, intent = _projection_ready(tmp_path)

    projection = project_wakeup_delivery(intent)
    assert projection.delivery_status == WAKEUP_PROJECTION_PENDING
    assert projection.canonical_source == "github-mailbox"
    assert projection.canonical_request_persisted is True
    assert projection.projection_only is True
    assert projection.executor_status == "NOT_TRIGGERED"
    assert "canonical request persisted" in projection.detail
    assert "Executor not yet triggered" in projection.detail
    assert projection.mailbox_ref == MAILBOX_REF
    assert projection.event_id == intent.event_id
    assert projection.event_digest == intent.event_digest
    assert projection.idempotency_key == intent.idempotency_key

    event = projection.to_human_event()
    assert event.kind == "SUBTASK_STARTED"
    assert event.status == "WAKEUP_PENDING"
    assert event.evidence_refs == (MAILBOX_REF, intent.event_id, intent.intent_id)
    serialized = json.dumps(projection.to_dict(), sort_keys=True)
    for forbidden in ("payload", "objective", "acceptance_criteria", "scope", "context"):
        assert forbidden not in serialized
    assert repository.read(MAILBOX_REF).events[0].envelope == envelope
    outbox.close()
    ledger.close()


def test_operator_projection_marks_failed_delivery_as_retrying_without_run_state(
    tmp_path: Path,
) -> None:
    from taskcontroller.controlplane.wakeup_outbox import (
        WAKEUP_ATTEMPT_FAILED,
        WAKEUP_TRANSPORT_UNAVAILABLE,
    )

    outbox, ledger, _, _, intent = _projection_ready(tmp_path)
    outbox.record_delivery_attempt(
        intent.intent_id,
        attempt_id="wakeup-delivery-projection-1",
        attempt_number=1,
        state=WAKEUP_ATTEMPT_FAILED,
        attempted_at="2026-09-11T06:30:04+07:00",
        retry_at="2026-09-11T06:30:14+07:00",
        error_code=WAKEUP_TRANSPORT_UNAVAILABLE,
    )

    projection = project_wakeup_delivery(
        outbox.get_intent(intent.intent_id),
        outbox.list_attempts(intent.intent_id),
    )
    assert projection.delivery_status == WAKEUP_PROJECTION_RETRYING
    assert projection.executor_status == "WAKEUP_RETRYING"
    assert projection.attempt_count == 1
    assert projection.next_attempt_at == "2026-09-11T06:30:14+07:00"
    assert "retrying" in projection.detail
    assert projection.canonical_request_persisted is True
    assert projection.projection_only is True
    assert project_wakeup_delivery(
        outbox.get_intent(intent.intent_id), outbox.list_attempts(intent.intent_id)
    ).to_human_event().status == "WAKEUP_RETRYING"
    outbox.close()
    ledger.close()


def test_operator_projection_marks_blocked_delivery_as_human_visible_not_run_state(
    tmp_path: Path,
) -> None:
    from taskcontroller.controlplane.wakeup_outbox import WAKEUP_ATTEMPT_BLOCKED

    outbox, ledger, _, _, intent = _projection_ready(tmp_path)
    outbox.record_delivery_attempt(
        intent.intent_id,
        attempt_id="wakeup-delivery-projection-blocked",
        attempt_number=1,
        state=WAKEUP_ATTEMPT_BLOCKED,
        attempted_at="2026-09-11T06:30:04+07:00",
        error_code="WAKEUP_DELIVERY_BLOCKED",
        error_detail="bounded delivery exhausted",
    )

    projection = project_wakeup_delivery(
        outbox.get_intent(intent.intent_id),
        outbox.list_attempts(intent.intent_id),
    )
    assert projection.delivery_status == WAKEUP_PROJECTION_BLOCKED
    assert projection.executor_status == "WAKEUP_BLOCKED"
    assert projection.canonical_request_persisted is True
    assert projection.projection_only is True
    assert "WAKEUP_DELIVERY_BLOCKED" in projection.detail
    event = projection.to_human_event()
    assert event.kind == "BLOCKED"
    assert event.status == "WAKEUP_BLOCKED"
    assert event.evidence_refs[0] == MAILBOX_REF
    outbox.close()
    ledger.close()


def test_operator_projection_rejects_attempts_not_bound_to_the_canonical_intent(
    tmp_path: Path,
) -> None:
    from dataclasses import replace
    from taskcontroller.controlplane.wakeup_outbox import (
        WAKEUP_ATTEMPT_FAILED,
        WAKEUP_TRANSPORT_UNAVAILABLE,
    )

    outbox, ledger, _, _, intent = _projection_ready(tmp_path)
    attempt = outbox.record_delivery_attempt(
        intent.intent_id,
        attempt_id="wakeup-delivery-projection-mismatch",
        attempt_number=1,
        state=WAKEUP_ATTEMPT_FAILED,
        attempted_at="2026-09-11T06:30:04+07:00",
        retry_at="2026-09-11T06:30:14+07:00",
        error_code=WAKEUP_TRANSPORT_UNAVAILABLE,
    )
    mismatched = replace(attempt, intent_id="wakeup-intent:foreign")

    with pytest.raises(TaskControllerValidationError, match="intent"):
        project_wakeup_delivery(intent, (mismatched,))
    outbox.close()
    ledger.close()
