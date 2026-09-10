from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import (
    A2AEnvelope,
    MailboxCursor,
    parse_mailbox_comment,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v1_contract_fixtures.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_v1_valid_envelopes_and_mailbox_bodies_round_trip() -> None:
    data = _fixture()

    for case_name in ("valid_request", "executor_progress", "terminal_result"):
        case = data["cases"][case_name]
        envelope = A2AEnvelope.from_dict(case["envelope"])
        assert envelope.to_dict() == case["envelope"]
        assert parse_mailbox_comment(case["mailbox_body"]) == envelope


def test_v1_duplicate_delivery_is_same_payload_and_stale_sequence_is_rejected() -> None:
    data = _fixture()["cases"]
    duplicate = data["duplicate_delivery"]
    first = A2AEnvelope.from_dict(duplicate["first"])
    retry = A2AEnvelope.from_dict(duplicate["retry"])
    assert retry == first

    stale = data["stale_sequence"]
    cursor = MailboxCursor.from_dict(stale["cursor"])
    candidate = A2AEnvelope.from_dict(stale["candidate"])
    with pytest.raises(TaskControllerValidationError):
        cursor.observe(candidate)


@pytest.mark.parametrize("case_name", ["missing_identity", "unsupported_protocol", "unsupported_kind"])
def test_v1_invalid_requests_fail_closed(case_name: str) -> None:
    payload = _fixture()["cases"][case_name]
    with pytest.raises(TaskControllerValidationError):
        A2AEnvelope.from_dict(payload)
