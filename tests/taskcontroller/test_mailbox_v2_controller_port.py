from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import (
    InMemoryMailboxRepository,
    MailboxRepository,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.runtime.mailbox import TaskControllerMailbox


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"


def _envelope() -> V2MailboxEnvelope:
    payload = copy.deepcopy(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]["execution_request"]
    )
    payload["message_id"] = "message-controller-port-1"
    payload["seq"] = 0
    payload["idempotency_key"] = "idem-controller-port-1"
    payload["payload"]["controller_port_test"] = True
    payload["execution_identity"]["attempt_id"] = "attempt-controller-port-1"
    payload["attempt"]["attempt_id"] = "attempt-controller-port-1"
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def test_controller_mailbox_delegates_the_repository_contract() -> None:
    repository = InMemoryMailboxRepository()
    mailbox = TaskControllerMailbox(repository)

    assert isinstance(mailbox.repository, MailboxRepository)
    assert mailbox.capabilities() == repository.capabilities()

    receipt = mailbox.write("controller-port", -1, _envelope())
    snapshot = mailbox.read("controller-port")
    assert snapshot.last_event_seq == 0
    assert mailbox.exact_readback(receipt) == snapshot
    assert mailbox.scan_after("controller-port", -1) == snapshot.events


def test_controller_mailbox_rejects_an_object_without_repository_contract() -> None:
    with pytest.raises(TaskControllerValidationError, match="MailboxRepository"):
        TaskControllerMailbox(object())


def test_controller_mailbox_module_has_no_github_comment_dependency() -> None:
    source = Path(TaskControllerMailbox.__module__.replace(".", "/") + ".py")
    if not source.is_absolute():
        source = Path(__file__).parents[2] / source
    assert "github_mailbox" not in source.read_text(encoding="utf-8")
