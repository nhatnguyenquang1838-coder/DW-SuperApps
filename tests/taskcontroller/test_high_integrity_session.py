from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.controlplane.request_compiler import BoundedMailboxRequest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import (
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
)
from taskcontroller.interaction.github_continuation_store import (
    GITHUB_CONTINUATION_RECORD_PROTOCOL,
    GitHubContinuationStore,
)
from taskcontroller.interaction.github_mailbox_v2 import (
    GITHUB_RECORD_PROTOCOL,
    GitHubIssueComment,
    GitHubMailboxRepository,
)
from taskcontroller.runtime.high_integrity_session import materialize_controller_transition


REPOSITORY = "owner/repo"
ISSUE = 839
CONTROLLER_MAILBOX = f"github://{REPOSITORY}/issues/{ISSUE}#controller-v2"
EXECUTOR_MAILBOX = f"github://{REPOSITORY}/issues/{ISSUE}#executor-v2"
SOURCE = {
    "repository": REPOSITORY,
    "commit_sha": "a" * 40,
    "path": "taskcontroller/runtime/high_integrity_session.py",
    "blob_digest": "sha256:" + "1" * 64,
}


class FakeGitHubComments:
    def __init__(self) -> None:
        self.comments: list[GitHubIssueComment] = []
        self.next_id = 1000

    def list_comments(self, repository: str, issue_number: int):
        assert repository == REPOSITORY
        assert issue_number == ISSUE
        return tuple(self.comments)

    def create_comment(self, repository: str, issue_number: int, body: str):
        assert repository == REPOSITORY
        assert issue_number == ISSUE
        comment = GitHubIssueComment(str(self.next_id), body)
        self.next_id += 1
        self.comments.append(comment)
        return comment


def _checkpoint() -> ControllerContinuation:
    return ControllerContinuation(
        run_id="run-839",
        controller_epoch=1,
        phase=ContinuationPhase.WAIT_EXECUTOR.value,
        status=ContinuationStatus.ACTIVE.value,
        next_action="POLL_EXECUTOR",
        controller_mailbox_ref=CONTROLLER_MAILBOX,
        controller_seq=1,
        executor_actor="hermes-cloud",
        executor_mailbox_ref=EXECUTOR_MAILBOX,
        expected_executor_seq=1,
        last_seen_executor_seq=0,
        wakeup_binding="slack-websocket",
        exact_head_sha="a" * 40,
        updated_at="2026-10-07T04:45:00Z",
    )


def _request(**changes: Any) -> BoundedMailboxRequest:
    values: dict[str, Any] = {
        "message_id": "message-839",
        "run_id": "run-839",
        "node_id": "SCRUM-839",
        "seq": 1,
        "correlation_id": "correlation-839",
        "contract_id": "contract-839",
        "plan_version": "plan-839",
        "contract_digest": "sha256:" + "3" * 64,
        "boundary_digest": "sha256:" + "4" * 64,
        "source_digest": "sha256:" + "5" * 64,
        "source_manifest_ref": "source-manifest-839",
        "objective": "Materialize one canonical mailbox/v2 transition.",
        "scope": {
            "allowed_actions": ["read_repo"],
            "denied_actions": ["merge", "deploy"],
            "writable_targets": [],
            "source_roots": ["taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "authority_constraints": {
            "denied_actions": ["merge", "deploy"],
            "writable_targets": [],
        },
        "acceptance_criteria": (
            "The mailbox transition is deterministic.",
            "No hand-authored transport record is accepted.",
        ),
        "source_refs": (SOURCE,),
        "evidence_refs": ("github://owner/repo/issues/140",),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "6" * 64,
        },
        "standards_profile_ref": "standards.default/v1",
        "recipient_capability": "taskcontroller.executor",
        "agent_instance": "hermes-cloud",
        "attempt_id": "attempt-839",
        "attempt_number": 1,
        "lease_generation": 1,
        "fencing_token": "fence-839",
        "lease_expires_at": "2026-10-07T05:45:00Z",
        "idempotency_key": "idem-839",
        "producer_namespace": "controller",
        "producer_actor_id": "chatgpt-controller",
        "payload": {
            "controller_contract_mode": "PLAN",
            "execution_authority_active": False,
        },
    }
    values.update(changes)
    return BoundedMailboxRequest(**values)


def _runtime(tmp_path: Path):
    transport = FakeGitHubComments()
    repository = GitHubMailboxRepository(transport)
    continuation = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )
    ledger = AuditFacade(tmp_path / "dispatch.sqlite3")
    return transport, repository, continuation, ledger


def test_materializer_owns_event_cursor_and_continuation_records(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        receipt = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:45:01Z",
            committed_at="2026-10-07T04:45:02Z",
        )
    finally:
        ledger.close()

    assert receipt.authority_granted is False
    assert receipt.envelope.protocol == "dw.taskcontroller.mailbox/v2"
    assert receipt.dispatch.committed.readback_verified is True
    assert receipt.dispatch.committed.mailbox_seq == 0
    assert receipt.dispatch.cursor.last_event_seq == 0
    assert receipt.continuation == checkpoint

    records = [json.loads(comment.body) for comment in transport.comments]
    continuation_records = [
        value for value in records if value.get("protocol") == GITHUB_CONTINUATION_RECORD_PROTOCOL
    ]
    mailbox_records = [
        value for value in records if value.get("protocol") == GITHUB_RECORD_PROTOCOL
    ]
    assert len(continuation_records) == 1
    assert [value["record_type"] for value in mailbox_records] == ["event", "cursor"]
    assert mailbox_records[0]["payload"]["event_seq"] == 0
    assert mailbox_records[0]["payload"]["previous_event_digest"] is None
    assert mailbox_records[1]["payload"]["last_event_seq"] == 0


def test_materializer_retry_is_idempotent_without_duplicate_remote_records(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        first = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:46:01Z",
            committed_at="2026-10-07T04:46:02Z",
        )
        comment_count = len(transport.comments)
        second = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:46:01Z",
            committed_at="2026-10-07T04:46:02Z",
        )
    finally:
        ledger.close()

    assert second.envelope.digest() == first.envelope.digest()
    assert second.dispatch.committed == first.dispatch.committed
    assert second.dispatch.cursor == first.dispatch.cursor
    assert len(transport.comments) == comment_count


@pytest.mark.parametrize(
    "payload, code",
    [
        (
            {"record_type": "disposition_release"},
            "HAND_AUTHORED_TRANSPORT_FIELD_FORBIDDEN",
        ),
        (
            {"approval_token": "raw-sensitive-value"},
            "SECRET_BEARING_PAYLOAD_FORBIDDEN",
        ),
    ],
)
def test_materializer_rejects_manual_transport_and_secret_payload_before_write(
    tmp_path: Path,
    payload: dict[str, Any],
    code: str,
) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    try:
        with pytest.raises(TaskControllerValidationError, match=code):
            materialize_controller_transition(
                continuation_store=continuation,
                repository=repository,
                ledger=ledger,
                checkpoint=_checkpoint(),
                request=_request(payload=payload),
                state_version=0,
                prepared_at="2026-10-07T04:47:01Z",
                committed_at="2026-10-07T04:47:02Z",
            )
    finally:
        ledger.close()

    assert transport.comments == []


def test_request_mapping_cannot_supply_remote_record_fields(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    request = _request().__dict__.copy()
    request["record_type"] = "disposition_release"
    try:
        with pytest.raises(TaskControllerValidationError):
            materialize_controller_transition(
                continuation_store=continuation,
                repository=repository,
                ledger=ledger,
                checkpoint=_checkpoint(),
                request=request,
                state_version=0,
                prepared_at="2026-10-07T04:48:01Z",
                committed_at="2026-10-07T04:48:02Z",
            )
    finally:
        ledger.close()

    assert transport.comments == []
