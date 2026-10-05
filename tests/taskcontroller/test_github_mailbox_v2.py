from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.github_mailbox_v2 import (
    GITHUB_RECORD_PROTOCOL,
    GitHubIssueComment,
    GitHubIssueCommentTransport,
    GitHubMailboxRepository,
)
from taskcontroller.interaction.mailbox_repository import MailboxRepository
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    V2MailboxEnvelope,
    canonical_digest,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
MAILBOX = "github://owner/repo/issues/575#controller-v2"


class FakeGitHubComments:
    def __init__(self) -> None:
        self.comments: list[GitHubIssueComment] = []
        self.calls: list[tuple[str, str, int]] = []
        self.next_id = 1000

    def list_comments(self, repository: str, issue_number: int):
        self.calls.append(("list", repository, issue_number))
        return tuple(self.comments)

    def create_comment(self, repository: str, issue_number: int, body: str):
        self.calls.append(("create", repository, issue_number))
        comment = GitHubIssueComment(comment_id=str(self.next_id), body=body)
        self.next_id += 1
        self.comments.append(comment)
        return comment

    def append_foreign(self, body: str) -> None:
        self.comments.append(GitHubIssueComment(comment_id=str(self.next_id), body=body))
        self.next_id += 1

    def replace_body(self, comment_id: str, body: str) -> None:
        self.comments = [
            GitHubIssueComment(comment_id=item.comment_id, body=body)
            if item.comment_id == comment_id
            else item
            for item in self.comments
        ]


def _envelope(**changes) -> V2MailboxEnvelope:
    payload = copy.deepcopy(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]["execution_request"]
    )
    payload["run_id"] = "scrum781-q0-20260920T074727Z"
    payload["node_id"] = "SCRUM-781-Q0"
    payload["message_id"] = "scrum781-controller-v2-1"
    payload["seq"] = 0
    payload["idempotency_key"] = "scrum781-controller-v2-1"
    payload["producer"] = {
        "namespace": "controller",
        "actor_id": "chatgpt-controller",
        "role": "controller",
    }
    payload["recipient"] = {
        "capability": "taskcontroller.executor",
        "agent_instance": "hermes-cloud",
    }
    payload["execution_identity"]["run_id"] = payload["run_id"]
    payload["execution_identity"]["node_id"] = payload["node_id"]
    payload["execution_identity"]["attempt_id"] = "attempt-scrum781-v2-1"
    payload["attempt"]["attempt_id"] = "attempt-scrum781-v2-1"
    payload["payload"] = {"request": "Materialize a high-integrity controller mailbox."}
    for key, value in changes.items():
        if key == "producer_namespace":
            payload["producer"]["namespace"] = value
        else:
            payload[key] = value
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _repo():
    transport = FakeGitHubComments()
    return GitHubMailboxRepository(transport), transport


def test_adapter_implements_mailbox_repository_protocol() -> None:
    repository, transport = _repo()

    assert isinstance(transport, GitHubIssueCommentTransport)
    assert isinstance(repository, MailboxRepository)
    caps = repository.capabilities()
    assert caps["protocol"] == "dw.taskcontroller.mailbox/v2"
    assert caps["adapter"] == "github_issue_comments"
    assert caps["append_only"] is True
    assert caps["single_writer_required"] is True
    assert caps["cross_process_multi_writer_cas"] is False
    assert caps["supports_v1"] is False
    assert caps["supports_v2"] is True


def test_append_read_and_exact_readback_are_canonical() -> None:
    repository, transport = _repo()
    envelope = _envelope()

    receipt = repository.write(MAILBOX, -1, envelope)
    snapshot = repository.exact_readback(receipt)

    assert receipt.event_seq == 0
    assert receipt.event_id == f"{MAILBOX}:event-0"
    assert receipt.envelope_digest == envelope.digest()
    assert receipt.idempotent is False
    assert snapshot.last_event_seq == 0
    assert snapshot.events[0].envelope == envelope
    assert snapshot.accepted_state["last_event_digest"] == receipt.event_digest
    assert len(transport.comments) == 1

    record = json.loads(transport.comments[0].body)
    assert record["protocol"] == GITHUB_RECORD_PROTOCOL
    assert record["record_type"] == "event"
    assert record["mailbox_ref"] == MAILBOX
    assert record["payload"]["digest"] == receipt.event_digest


def test_idempotent_replay_returns_same_receipt_without_new_comment() -> None:
    repository, transport = _repo()
    envelope = _envelope()

    first = repository.write(MAILBOX, -1, envelope)
    second = repository.write(MAILBOX, 0, envelope)

    assert second.event_id == first.event_id
    assert second.event_digest == first.event_digest
    assert second.idempotent is True
    assert len(transport.comments) == 1


def test_conflicting_idempotency_key_fails_closed() -> None:
    repository, transport = _repo()
    repository.write(MAILBOX, -1, _envelope())

    with pytest.raises(TaskControllerValidationError) as caught:
        repository.write(
            MAILBOX,
            0,
            _envelope(
                message_id="different-message",
                payload={"request": "different"},
            ),
        )

    assert getattr(caught.value, "code", None) == MailboxV2ErrorCode.DIGEST_MISMATCH
    assert len(transport.comments) == 1


def test_expected_sequence_mismatch_fails_before_append() -> None:
    repository, transport = _repo()

    with pytest.raises(TaskControllerValidationError) as caught:
        repository.write(MAILBOX, 0, _envelope())

    assert getattr(caught.value, "code", None) == MailboxV2ErrorCode.INVALID_SEQUENCE
    assert transport.comments == []


def test_foreign_and_other_mailbox_comments_are_ignored() -> None:
    repository, transport = _repo()
    transport.append_foreign("human discussion")
    transport.append_foreign('{"protocol":"something-else","payload":{}}')
    repository.write(MAILBOX, -1, _envelope())

    other = json.loads(transport.comments[-1].body)
    other["mailbox_ref"] = "github://owner/repo/issues/575#executor-v2"
    transport.append_foreign(json.dumps(other, sort_keys=True, separators=(",", ":")))

    snapshot = repository.read(MAILBOX)

    assert snapshot.last_event_seq == 0
    assert len(snapshot.events) == 1


def test_malformed_tagged_comment_fails_closed() -> None:
    repository, transport = _repo()
    transport.append_foreign(
        '{"protocol":"dw.taskcontroller.github-mailbox-record/v1","record_type":'
    )

    with pytest.raises(TaskControllerValidationError) as caught:
        repository.read(MAILBOX)

    assert getattr(caught.value, "code", None) == MailboxV2ErrorCode.SCHEMA_INVALID


def test_mutated_event_payload_is_detected_by_semantic_digest() -> None:
    repository, transport = _repo()
    receipt = repository.write(MAILBOX, -1, _envelope())

    record = json.loads(transport.comments[0].body)
    record["payload"]["envelope"]["payload"]["request"] = "tampered"
    transport.replace_body(
        transport.comments[0].comment_id,
        json.dumps(record, sort_keys=True, separators=(",", ":")),
    )

    with pytest.raises(TaskControllerValidationError) as caught:
        repository.exact_readback(receipt)

    assert getattr(caught.value, "code", None) in {
        MailboxV2ErrorCode.DIGEST_MISMATCH,
        MailboxV2ErrorCode.CONTRACT_MISMATCH,
    }


def test_cursor_acknowledgement_is_append_only_and_exact() -> None:
    repository, transport = _repo()
    event = repository.write(MAILBOX, -1, _envelope())
    snapshot = repository.exact_readback(event)

    initial = repository.read_cursor(
        MAILBOX,
        "scrum781-q0-20260920T074727Z",
        "SCRUM-781-Q0",
        "controller",
    )
    assert initial.last_event_seq == -1

    advanced = initial.observe(snapshot.events[0])
    persisted = repository.acknowledge_cursor(advanced)

    assert persisted == advanced
    assert repository.read_cursor(
        MAILBOX,
        "scrum781-q0-20260920T074727Z",
        "SCRUM-781-Q0",
        "controller",
    ) == advanced
    assert len(transport.comments) == 2
    record = json.loads(transport.comments[1].body)
    assert record["record_type"] == "cursor"
    assert record["payload"]["last_event_digest"] == event.event_digest


def test_scan_after_cursor_filters_to_bound_actor_identity() -> None:
    repository, _ = _repo()
    first = repository.write(MAILBOX, -1, _envelope())
    first_snapshot = repository.exact_readback(first)
    cursor = repository.read_cursor(
        MAILBOX,
        "scrum781-q0-20260920T074727Z",
        "SCRUM-781-Q0",
        "controller",
    ).observe(first_snapshot.events[0])
    repository.acknowledge_cursor(cursor)

    second = _envelope(
        seq=1,
        message_id="scrum781-controller-v2-2",
        idempotency_key="scrum781-controller-v2-2",
    )
    repository.write(MAILBOX, 0, second)

    events = repository.scan_after_cursor(cursor)
    assert len(events) == 1
    assert events[0].logical_seq == 1
    assert events[0].producer_namespace == "controller"


def test_conflicting_or_regressing_cursor_is_rejected() -> None:
    repository, _ = _repo()
    receipt = repository.write(MAILBOX, -1, _envelope())
    event = repository.exact_readback(receipt).events[0]
    initial = repository.read_cursor(
        MAILBOX,
        event.envelope.run_id,
        event.envelope.node_id,
        event.producer_namespace,
    )
    advanced = initial.observe(event)
    repository.acknowledge_cursor(advanced)

    with pytest.raises(TaskControllerValidationError):
        repository.acknowledge_cursor(initial)


def test_invalid_mailbox_ref_fails_closed() -> None:
    repository, _ = _repo()

    with pytest.raises(TaskControllerValidationError):
        repository.read("github://owner/repo/issues/575")


def test_transport_body_whitespace_is_not_semantic_identity() -> None:
    repository, transport = _repo()
    receipt = repository.write(MAILBOX, -1, _envelope())

    parsed = json.loads(transport.comments[0].body)
    transport.replace_body(
        transport.comments[0].comment_id,
        json.dumps(parsed, ensure_ascii=False, indent=2),
    )

    snapshot = repository.exact_readback(receipt)
    assert snapshot.events[0].event_digest == receipt.event_digest
