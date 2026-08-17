from __future__ import annotations

import pytest

from taskcontroller.audit.facade import NoOpAuditFacade
from taskcontroller.domain.values import InputRef
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import (
    A2AEnvelope,
    EnvelopeKind,
    HumanEventKind,
    MailboxCursor,
    audit_event_from_envelope,
    mailbox_operation,
    parse_mailbox_comment,
    project_envelope_for_human,
    record_envelope_event,
    render_mailbox_comment,
)


def _envelope(**overrides) -> A2AEnvelope:
    data = {
        "run_id": "run.tc.57",
        "node_id": "node.mailbox",
        "sender": "hermes-cloud",
        "recipient": "controller",
        "seq": 7,
        "kind": EnvelopeKind.REPORT.value,
        "inputs": [
            InputRef(
                input_id="execution-context",
                source_ref="github://nhatnguyenquang1838-coder/DW-SuperApps@abc123/taskcontroller/domain/values.py#L1-L20",
                media_type="text/x-python",
            )
        ],
        "artifact_refs": ["github://nhatnguyenquang1838-coder/DW-SuperApps/pull/999@abc123"],
        "request": "Review the bounded mailbox slice.",
        "state": {"status": "DONE"},
        "updated_at": "2026-08-16T23:30:00+07:00",
    }
    data.update(overrides)
    return A2AEnvelope(**data)


def test_envelope_round_trip_is_deterministic_and_reference_based() -> None:
    envelope = _envelope()

    payload = envelope.to_dict()
    rebuilt = A2AEnvelope.from_dict(payload)

    assert rebuilt == envelope
    assert rebuilt.to_dict() == payload
    assert payload["protocol"] == "dw.taskcontroller.a2a/v1"
    assert payload["inputs"] == [
        {
            "input_id": "execution-context",
            "source_ref": "github://nhatnguyenquang1838-coder/DW-SuperApps@abc123/taskcontroller/domain/values.py#L1-L20",
            "media_type": "text/x-python",
        }
    ]
    assert "file_body" not in payload
    assert "thread_history" not in payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"run_id": ""},
        {"node_id": ""},
        {"sender": ""},
        {"recipient": ""},
        {"seq": 0},
        {"seq": -1},
        {"kind": "CHATTER"},
        {"updated_at": ""},
    ],
)
def test_envelope_invalid_core_fields_fail_closed(overrides: dict) -> None:
    with pytest.raises(TaskControllerValidationError):
        _envelope(**overrides)


def test_cursor_accepts_only_strictly_newer_sequence_for_same_actor() -> None:
    cursor = MailboxCursor(actor="hermes-cloud", last_seen_seq=6, mailbox_ref="comment:123")

    next_cursor = cursor.observe(_envelope(seq=7))

    assert next_cursor.last_seen_seq == 7
    assert next_cursor.actor == "hermes-cloud"
    assert next_cursor.mailbox_ref == "comment:123"

    with pytest.raises(TaskControllerValidationError):
        next_cursor.observe(_envelope(seq=7))

    with pytest.raises(TaskControllerValidationError):
        next_cursor.observe(_envelope(seq=5))

    with pytest.raises(TaskControllerValidationError):
        next_cursor.observe(_envelope(sender="codex", seq=8))


def test_cursor_round_trip_supports_recovery_without_chat_history() -> None:
    cursor = MailboxCursor(
        actor="hermes-cloud",
        last_seen_seq=11,
        mailbox_ref="comment:123",
        last_head_sha="deadbeef",
    )

    recovered = MailboxCursor.from_dict(cursor.to_dict())

    assert recovered == cursor
    assert recovered.to_dict() == {
        "actor": "hermes-cloud",
        "last_seen_seq": 11,
        "mailbox_ref": "comment:123",
        "last_head_sha": "deadbeef",
    }


def test_github_mailbox_comment_round_trip_has_one_actor_marker() -> None:
    envelope = _envelope()

    body = render_mailbox_comment(envelope)
    parsed = parse_mailbox_comment(body)

    assert body.count("<!-- taskcontroller:mailbox:hermes-cloud -->") == 1
    assert parsed == envelope
    assert "Latest seq: 7" in body
    assert "github://nhatnguyenquang1838-coder/DW-SuperApps@abc123" not in body.split("```json", 1)[0]


def test_mailbox_parser_rejects_sender_marker_mismatch_and_multiple_markers() -> None:
    body = render_mailbox_comment(_envelope())

    with pytest.raises(TaskControllerValidationError):
        parse_mailbox_comment(body.replace("mailbox:hermes-cloud", "mailbox:codex", 1))

    with pytest.raises(TaskControllerValidationError):
        parse_mailbox_comment("<!-- taskcontroller:mailbox:hermes-cloud -->\n" + body)


def test_mailbox_operation_preserves_one_actor_one_comment_semantics() -> None:
    assert mailbox_operation(None) == "CREATE_COMMENT"
    assert mailbox_operation(12345) == "UPDATE_COMMENT"


def test_human_projection_compacts_machine_events() -> None:
    assert project_envelope_for_human(_envelope(kind=EnvelopeKind.HEALTH.value)) is None

    review = project_envelope_for_human(_envelope(kind=EnvelopeKind.REVIEW_REQUEST.value))
    assert review is not None
    assert review.kind == HumanEventKind.REVIEW_REQUIRED.value
    assert "```json" not in review.detail
    assert "execution-context" not in review.detail

    correction = project_envelope_for_human(_envelope(kind=EnvelopeKind.CORRECTION.value))
    assert correction is not None
    assert correction.kind == HumanEventKind.CORRECTION_REQUIRED.value

    terminal = project_envelope_for_human(_envelope(kind=EnvelopeKind.TERMINAL.value))
    assert terminal is not None
    assert terminal.kind == HumanEventKind.TERMINAL.value


def test_report_projects_to_one_human_milestone_not_raw_protocol() -> None:
    event = project_envelope_for_human(_envelope(kind=EnvelopeKind.REPORT.value))

    assert event is not None
    assert event.kind == HumanEventKind.MILESTONE_REACHED.value
    assert event.evidence_refs == (
        "github://nhatnguyenquang1838-coder/DW-SuperApps/pull/999@abc123",
    )
    assert "protocol" not in event.detail.lower()


def test_a2a_audit_event_is_semantic_reference_evidence() -> None:
    envelope = _envelope()

    event = audit_event_from_envelope(
        envelope,
        event_id="evt.a2a.7",
        raw_payload_ref="github://nhatnguyenquang1838-coder/DW-SuperApps/issues/57#comment-123",
    )

    assert event.event_id == "evt.a2a.7"
    assert event.run_id == envelope.run_id
    assert event.node_id == envelope.node_id
    assert event.actor == envelope.sender
    assert event.source == "taskcontroller.interaction"
    assert event.decision_kind == "A2A_REPORT"
    assert event.sequence == envelope.seq
    assert event.timestamp == envelope.updated_at
    assert event.raw_payload_ref.endswith("#comment-123")
    assert event.evidence_refs == (
        "github://nhatnguyenquang1838-coder/DW-SuperApps@abc123/taskcontroller/domain/values.py#L1-L20",
        "github://nhatnguyenquang1838-coder/DW-SuperApps/pull/999@abc123",
    )
    assert "```json" not in event.payload_summary
    assert "execution-context" not in event.payload_summary
    assert len(event.payload_summary) <= 300


def test_record_envelope_event_uses_audit_facade_contract() -> None:
    recorded = record_envelope_event(
        NoOpAuditFacade(),
        _envelope(),
        event_id="evt.noop.7",
        raw_payload_ref="comment:123",
    )

    assert recorded == 0
