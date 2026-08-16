from __future__ import annotations

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import MailboxCursor, WakeupSignal


def _signal(**overrides) -> WakeupSignal:
    data = {
        "run_id": "TC-A2A-PILOT-20260816-01",
        "sender": "controller",
        "recipient": "hermes-cloud",
        "mailbox_ref": "github://nhatnguyenquang1838-coder/DW-SuperApps/issues/57#issuecomment-5308536445",
        "seq": 2,
        "updated_at": "2026-08-16T23:54:00+07:00",
    }
    data.update(overrides)
    return WakeupSignal(**data)


def test_wakeup_signal_round_trip_is_pointer_only() -> None:
    signal = _signal()

    payload = signal.to_dict()
    rebuilt = WakeupSignal.from_dict(payload)

    assert rebuilt == signal
    assert payload == {
        "protocol": "dw.taskcontroller.wakeup/v1",
        "run_id": "TC-A2A-PILOT-20260816-01",
        "sender": "controller",
        "recipient": "hermes-cloud",
        "mailbox_ref": "github://nhatnguyenquang1838-coder/DW-SuperApps/issues/57#issuecomment-5308536445",
        "seq": 2,
        "updated_at": "2026-08-16T23:54:00+07:00",
    }
    for forbidden in ("request", "inputs", "artifact_refs", "state", "command"):
        assert forbidden not in payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"run_id": ""},
        {"sender": ""},
        {"recipient": ""},
        {"mailbox_ref": ""},
        {"seq": 0},
        {"seq": -1},
        {"updated_at": ""},
    ],
)
def test_wakeup_signal_invalid_fields_fail_closed(overrides: dict) -> None:
    with pytest.raises(TaskControllerValidationError):
        _signal(**overrides)


def test_wakeup_announces_only_unseen_work_for_recipient_cursor() -> None:
    cursor = MailboxCursor(
        actor="hermes-cloud",
        last_seen_seq=1,
        mailbox_ref="github://nhatnguyenquang1838-coder/DW-SuperApps/issues/57#issuecomment-5308548539",
    )

    assert _signal(seq=2).announces_new_work(cursor) is True
    assert _signal(seq=1).announces_new_work(cursor) is False

    with pytest.raises(TaskControllerValidationError):
        _signal(recipient="codex", seq=2).announces_new_work(cursor)


def test_wakeup_protocol_mismatch_fails_closed() -> None:
    payload = _signal().to_dict()
    payload["protocol"] = "dw.taskcontroller.a2a/v1"

    with pytest.raises(TaskControllerValidationError):
        WakeupSignal.from_dict(payload)
