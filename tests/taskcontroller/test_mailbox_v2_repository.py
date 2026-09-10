from __future__ import annotations

import copy
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.errors import TaskControllerValidationError


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
V2_PROTOCOL = "dw.taskcontroller.mailbox/v2"


def _api():
    """Load the desired additive repository API so a missing module is RED."""
    try:
        from taskcontroller.interaction.mailbox_repository import (
            InMemoryMailboxRepository,
            MailboxEvent,
            MailboxRepository,
            WriteReceipt,
        )
        from taskcontroller.interaction.mailbox_v2 import canonical_digest
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"v2 mailbox repository module is missing: {exc}")
    return InMemoryMailboxRepository, MailboxEvent, MailboxRepository, WriteReceipt, canonical_digest


def _fixture_payload() -> dict[str, Any]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(data["cases"]["execution_request"])


def _envelope(
    *,
    producer: str = "controller",
    seq: int = 0,
    message_id: str = "message-repository-1",
    idempotency_key: str = "idem-repository-1",
) -> Any:
    _, _, _, _, canonical_digest = _api()
    payload = _fixture_payload()
    payload["message_id"] = message_id
    payload["seq"] = seq
    payload["idempotency_key"] = idempotency_key
    payload["producer"] = {
        "namespace": producer,
        "actor_id": f"{producer}-actor",
        "role": "controller",
    }
    payload["execution_identity"]["attempt_id"] = f"attempt-{producer}-{seq}"
    payload["attempt"]["attempt_id"] = payload["execution_identity"]["attempt_id"]
    payload["payload"]["repository_test_producer"] = producer
    payload["digest"] = canonical_digest(payload)
    from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope

    return V2MailboxEnvelope.from_dict(payload)


def _assert_code(operation, expected: str) -> None:
    with pytest.raises(TaskControllerValidationError) as caught:
        operation()
    assert getattr(caught.value, "code", None) == expected


def test_repository_protocol_and_empty_snapshot_are_deterministic() -> None:
    InMemoryMailboxRepository, _, MailboxRepository, _, _ = _api()
    repo = InMemoryMailboxRepository()
    assert isinstance(repo, MailboxRepository)
    capabilities = repo.capabilities()
    assert capabilities["protocol"] == "dw.taskcontroller.mailbox/v2"
    assert capabilities["append_only"] is True
    assert capabilities["supports_v1"] is False
    assert capabilities["operations"] == ["read", "write", "exact_readback", "scan_after"]
    first = repo.read("mailbox-empty")
    second = repo.read("mailbox-empty")
    assert first == second
    assert first.last_event_seq == -1
    assert first.events == ()
    assert first.accepted_state == {
        "accepted_event_ids": [],
        "last_event_digest": None,
        "last_event_seq": -1,
        "producer_sequences": {},
    }


def test_write_binds_immutable_event_and_exact_readback_receipt() -> None:
    InMemoryMailboxRepository, MailboxEvent, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    envelope = _envelope()
    receipt = repo.write("mailbox-1", -1, envelope)
    assert receipt.mailbox_ref == "mailbox-1"
    assert receipt.event_seq == 0
    assert receipt.event_id == "mailbox-1:event-0"
    assert receipt.envelope_digest == envelope.digest()
    snapshot = repo.exact_readback(receipt)
    assert len(snapshot.events) == 1
    event = snapshot.events[0]
    assert isinstance(event, MailboxEvent)
    assert event.event_id == receipt.event_id
    assert event.producer_namespace == "controller"
    assert event.logical_seq == 0
    assert event.previous_event_digest is None
    assert event.envelope_digest == envelope.digest()
    assert event.event_digest == receipt.event_digest
    assert repo.scan_after("mailbox-1", -1) == (event,)


def test_concurrent_writers_have_one_cas_winner_without_overwrite() -> None:
    InMemoryMailboxRepository, _, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def writer(producer: str) -> None:
        barrier.wait()
        try:
            results.append(
                (
                    "ok",
                    repo.write(
                        "mailbox-cas",
                        -1,
                        _envelope(producer=producer, idempotency_key=f"idem-{producer}"),
                    ),
                )
            )
        except TaskControllerValidationError as exc:
            results.append(("error", exc.code))

    threads = [threading.Thread(target=writer, args=(producer,)) for producer in ("controller-a", "controller-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(kind for kind, _ in results) == ["error", "ok"]
    assert [value for kind, value in results if kind == "error"] == ["INVALID_SEQUENCE"]
    assert len(repo.read("mailbox-cas").events) == 1


def test_duplicate_same_idempotency_and_digest_is_noop() -> None:
    InMemoryMailboxRepository, _, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    envelope = _envelope()
    first = repo.write("mailbox-idempotent", -1, envelope)
    retry = repo.write("mailbox-idempotent", -1, envelope)
    assert first.event_id == retry.event_id
    assert first.event_digest == retry.event_digest
    assert retry.idempotent is True
    assert len(repo.read("mailbox-idempotent").events) == 1


def test_duplicate_same_idempotency_with_different_digest_is_rejected() -> None:
    InMemoryMailboxRepository, _, _, _, canonical_digest = _api()
    repo = InMemoryMailboxRepository()
    first = _envelope()
    repo.write("mailbox-conflict", -1, first)
    conflicting = _envelope(message_id="message-repository-conflict")
    conflicting_payload = conflicting.to_dict()
    conflicting_payload["idempotency_key"] = first.idempotency_key
    conflicting_payload["payload"]["objective"] = "conflicting objective"
    conflicting_payload["digest"] = canonical_digest(conflicting_payload)
    from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope

    conflicting = V2MailboxEnvelope.from_dict(conflicting_payload)
    _assert_code(
        lambda: repo.write("mailbox-conflict", -1, conflicting),
        "DIGEST_MISMATCH",
    )
    assert len(repo.read("mailbox-conflict").events) == 1


def test_per_producer_sequence_and_append_chain_are_enforced() -> None:
    InMemoryMailboxRepository, _, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    first = repo.write("mailbox-chain", -1, _envelope(seq=0))
    executor = repo.write(
        "mailbox-chain",
        0,
        _envelope(producer="executor", seq=0, message_id="message-executor-1", idempotency_key="idem-executor-1"),
    )
    controller_next = repo.write(
        "mailbox-chain",
        1,
        _envelope(seq=1, message_id="message-controller-2", idempotency_key="idem-controller-2"),
    )
    assert executor.event_seq == 1
    assert controller_next.event_seq == 2
    events = repo.read("mailbox-chain").events
    assert [event.previous_event_digest for event in events] == [None, first.event_digest, executor.event_digest]
    _assert_code(
        lambda: repo.write(
            "mailbox-chain",
            2,
            _envelope(seq=0, message_id="message-controller-stale", idempotency_key="idem-controller-stale"),
        ),
        "INVALID_SEQUENCE",
    )


def test_scan_after_and_accepted_projection_replay_are_byte_equivalent() -> None:
    InMemoryMailboxRepository, _, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    repo.write("mailbox-read-model", -1, _envelope(seq=0))
    repo.write(
        "mailbox-read-model",
        0,
        _envelope(producer="executor", seq=0, message_id="message-executor-read", idempotency_key="idem-executor-read"),
    )
    repo.write(
        "mailbox-read-model",
        1,
        _envelope(seq=1, message_id="message-controller-read", idempotency_key="idem-controller-read"),
    )
    first = repo.read("mailbox-read-model")
    second = repo.read("mailbox-read-model")
    assert first.accepted_state == second.accepted_state
    assert first.to_dict() == second.to_dict()
    assert [event.event_seq for event in repo.scan_after("mailbox-read-model", 0)] == [1, 2]


def test_exact_readback_rejects_receipt_digest_mismatch() -> None:
    InMemoryMailboxRepository, _, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    receipt = repo.write("mailbox-readback", -1, _envelope())
    corrupted = replace(receipt, event_digest="sha256:" + "0" * 64)
    _assert_code(lambda: repo.exact_readback(corrupted), "DIGEST_MISMATCH")


def test_invalid_raw_payload_is_quarantined_without_event_or_execution() -> None:
    InMemoryMailboxRepository, _, _, _, _ = _api()
    repo = InMemoryMailboxRepository()
    quarantine = repo.quarantine_invalid("mailbox-quarantine", {"protocol": V2_PROTOCOL})
    assert quarantine.error_code == "SCHEMA_INVALID"
    assert quarantine.mailbox_ref == "mailbox-quarantine"
    assert repo.read("mailbox-quarantine").events == ()
    assert repo.quarantined("mailbox-quarantine") == (quarantine,)
