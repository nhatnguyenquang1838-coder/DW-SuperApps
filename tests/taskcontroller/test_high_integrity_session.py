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
from taskcontroller.interaction.mailbox_repository import MailboxActorCursor
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.interaction.executor_entrypoint import V2ExecutorValidationPolicy
from taskcontroller.runtime.dispatch_ledger import DISPATCH_COMMITTED
from taskcontroller.runtime.high_integrity_session import (
    WAIT_EXECUTOR_AUTHORITY_ACTION,
    bootstrap_executor_v2,
    materialize_controller_transition,
    recover_high_integrity_session,
    resume_controller_v2,
)


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
    def __init__(self, *, crash_on_create: int | None = None) -> None:
        self.comments: list[GitHubIssueComment] = []
        self.next_id = 1000
        self.create_calls = 0
        self.crash_on_create = crash_on_create
        self.crashed = False

    def list_comments(self, repository: str, issue_number: int):
        assert repository == REPOSITORY
        assert issue_number == ISSUE
        return tuple(self.comments)

    def create_comment(self, repository: str, issue_number: int, body: str):
        assert repository == REPOSITORY
        assert issue_number == ISSUE
        self.create_calls += 1
        if (
            self.crash_on_create is not None
            and self.create_calls == self.crash_on_create
            and not self.crashed
        ):
            self.crashed = True
            raise RuntimeError("synthetic GitHub comment crash")
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


def _runtime(tmp_path: Path, transport: FakeGitHubComments | None = None):
    transport = transport or FakeGitHubComments()
    repository = GitHubMailboxRepository(transport)
    continuation = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )
    ledger = AuditFacade(tmp_path / "dispatch.sqlite3")
    return transport, repository, continuation, ledger


def _progress(request: V2MailboxEnvelope, *, seq: int = 1) -> V2MailboxEnvelope:
    payload = request.to_dict()
    payload["message_id"] = "progress-839"
    payload["seq"] = seq
    payload["direction"] = "executor_to_controller"
    payload["message_type"] = "execution_progress"
    payload["producer"] = {
        "namespace": "hermes-executor",
        "actor_id": "hermes-cloud",
        "role": "executor",
    }
    payload["recipient"] = {
        "capability": "taskcontroller.controller",
        "agent_instance": "controller",
    }
    payload["payload"] = {
        "status": "SUCCEEDED",
        "report_type": "mission_status",
        "typed_next": "COMPLETE",
    }
    payload["provenance"] = {
        "origin": "executor",
        "parent_message_id": request.to_dict()["message_id"],
        "child_id": None,
        "lens": "execution",
        "agent_instance": request.attempt["agent_instance"],
        "status": "SUCCEEDED",
        "source_refs": [],
        "evidence_refs": [],
        "result_digest": None,
    }
    payload["idempotency_key"] = "progress-idem-839"
    payload.pop("result", None)
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


class CrashAfterEventBeforeLedgerCommit(GitHubMailboxRepository):
    def __init__(self, transport: FakeGitHubComments) -> None:
        super().__init__(transport)
        self.readback_calls = 0
        self.crashed = False

    def exact_readback(self, receipt):
        snapshot = super().exact_readback(receipt)
        self.readback_calls += 1
        if self.readback_calls == 1 and not self.crashed:
            self.crashed = True
            raise RuntimeError("synthetic crash after event before ledger commit")
        return snapshot


class CrashAfterLedgerCommit:
    def __init__(self, ledger: AuditFacade) -> None:
        self.ledger = ledger
        self.crashed = False

    def record(self, run_id: str, event):
        result = self.ledger.record(run_id, event)
        if event.decision_kind == DISPATCH_COMMITTED and not self.crashed:
            self.crashed = True
            raise RuntimeError("synthetic crash after ledger commit")
        return result

    def events(self, run_id: str):
        return self.ledger.events(run_id)


class CrashBeforeContinuationReadback:
    def __init__(self, store: GitHubContinuationStore) -> None:
        self.store = store
        self.loads = 0
        self.crashed = False

    def save_manifest(self, manifest):
        return self.store.save_manifest(manifest)

    def load_manifest(self, run_id: str, manifest_kind: str):
        self.loads += 1
        if self.loads == 3 and not self.crashed:
            self.crashed = True
            raise RuntimeError("synthetic crash before post-cursor continuation readback")
        return self.store.load_manifest(run_id, manifest_kind)

    def latest_receipt(self, run_id: str, manifest_kind: str):
        return self.store.latest_receipt(run_id, manifest_kind)


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

def test_materializer_returns_exact_remote_event_cursor_and_continuation_receipts(
    tmp_path: Path,
) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    try:
        receipt = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=_checkpoint(),
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T05:00:01Z",
            committed_at="2026-10-07T05:00:02Z",
        )
    finally:
        ledger.close()

    assert receipt.event_remote.record_type == "event"
    assert receipt.event_remote.comment_ref.endswith("#issuecomment-1001")
    assert receipt.event_remote.payload["event_id"] == receipt.dispatch.committed.event_id
    assert receipt.cursor_remote.record_type == "cursor"
    assert receipt.cursor_remote.comment_ref.endswith("#issuecomment-1002")
    assert receipt.continuation_remote.record_seq == 0
    assert receipt.continuation_remote.comment_ref.endswith("#issuecomment-1000")
    assert receipt.continuation_remote.record_digest.startswith("sha256:")


@pytest.mark.parametrize(
    "environment",
    [
        {"GITHUB_TOKEN": "raw-secret"},
        {"nested": {"refresh_token": "raw-secret"}},
        {"oauth": {"session-token": "raw-secret"}},
    ],
)
def test_materializer_rejects_secret_bearing_non_payload_fields_before_write(
    tmp_path: Path,
    environment: dict[str, Any],
) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    try:
        with pytest.raises(TaskControllerValidationError, match="SECRET_BEARING_PAYLOAD_FORBIDDEN"):
            materialize_controller_transition(
                continuation_store=continuation,
                repository=repository,
                ledger=ledger,
                checkpoint=_checkpoint(),
                request=_request(environment_requirements=environment),
                state_version=0,
                prepared_at="2026-10-07T05:01:01Z",
                committed_at="2026-10-07T05:01:02Z",
            )
    finally:
        ledger.close()
    assert transport.comments == []


def test_mailbox_v2_full_lifecycle_survives_controller_restart(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        materialized = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T05:02:01Z",
            committed_at="2026-10-07T05:02:02Z",
        )

        signal = WakeupSignal(
            run_id=checkpoint.run_id,
            sender="controller",
            recipient="hermes-cloud",
            mailbox_ref=CONTROLLER_MAILBOX,
            seq=materialized.dispatch.committed.mailbox_seq + 1,
            updated_at="2026-10-07T05:02:03Z",
        )
        executor_request = bootstrap_executor_v2(
            repository,
            signal,
            executor_actor="hermes-cloud",
            validation_policy=V2ExecutorValidationPolicy(
                capability_id="taskcontroller.executor",
                instance_id="hermes-cloud",
                attempt_id="attempt-839",
                lease_generation=1,
                fencing_token="fence-839",
            ),
        )
        assert executor_request.envelope == materialized.envelope
        assert executor_request.cursor.last_event_id == materialized.dispatch.committed.event_id

        progress = _progress(materialized.envelope)
        repository.write(EXECUTOR_MAILBOX, -1, progress)
        result_cursor = MailboxActorCursor.initial(
            EXECUTOR_MAILBOX,
            run_id=progress.run_id,
            node_id=progress.node_id,
            actor_namespace="hermes-executor",
        )
        resumed = resume_controller_v2(
            continuation_store=continuation,
            repository=repository,
            checkpoint=checkpoint,
            cursor=result_cursor,
            correlation_id=progress.to_dict()["correlation_id"],
            expected_identity=progress.execution_identity,
            observed_at="2026-10-07T05:02:04Z",
        )
        assert resumed.checkpoint.phase == ContinuationPhase.REVIEW_EXECUTOR.value
        assert resumed.checkpoint.last_seen_executor_seq == 1
    finally:
        ledger.close()

    restarted_repository = GitHubMailboxRepository(transport)
    restarted_continuation = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )
    recovered = recover_high_integrity_session(
        continuation_store=restarted_continuation,
        repository=restarted_repository,
        run_id=checkpoint.run_id,
    )
    assert recovered.checkpoint == resumed.checkpoint
    assert recovered.controller_envelope == materialized.envelope
    assert recovered.controller_cursor.last_event_id == materialized.dispatch.committed.event_id
    durable_result_cursor = restarted_repository.read_cursor(
        EXECUTOR_MAILBOX,
        progress.run_id,
        progress.node_id,
        "hermes-executor",
    )
    assert durable_result_cursor.last_event_seq == 0
    assert durable_result_cursor.last_logical_seq == 1


def test_crash_after_continuation_before_event_retries_without_duplicate_state(
    tmp_path: Path,
) -> None:
    transport = FakeGitHubComments(crash_on_create=2)
    _, repository, continuation, ledger = _runtime(tmp_path, transport)
    try:
        with pytest.raises(RuntimeError, match="synthetic GitHub comment crash"):
            materialize_controller_transition(
                continuation_store=continuation,
                repository=repository,
                ledger=ledger,
                checkpoint=_checkpoint(),
                request=_request(),
                state_version=0,
                prepared_at="2026-10-07T05:03:01Z",
                committed_at="2026-10-07T05:03:02Z",
            )
        assert len(transport.comments) == 1

        receipt = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=_checkpoint(),
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T05:03:01Z",
            committed_at="2026-10-07T05:03:02Z",
        )
    finally:
        ledger.close()

    records = [json.loads(comment.body) for comment in transport.comments]
    assert sum(record.get("protocol") == GITHUB_CONTINUATION_RECORD_PROTOCOL for record in records) == 1
    assert [record.get("record_type") for record in records if record.get("protocol") == GITHUB_RECORD_PROTOCOL] == [
        "event",
        "cursor",
    ]
    assert receipt.continuation_remote.idempotent is True


def test_crash_after_event_before_ledger_commit_repairs_without_duplicate_event(
    tmp_path: Path,
) -> None:
    transport = FakeGitHubComments()
    repository = CrashAfterEventBeforeLedgerCommit(transport)
    continuation = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )
    ledger = AuditFacade(tmp_path / "event-before-ledger.sqlite3")
    try:
        with pytest.raises(RuntimeError, match="event before ledger commit"):
            materialize_controller_transition(
                continuation_store=continuation,
                repository=repository,
                ledger=ledger,
                checkpoint=_checkpoint(),
                request=_request(),
                state_version=0,
                prepared_at="2026-10-07T05:03:31Z",
                committed_at="2026-10-07T05:03:32Z",
            )
        assert len(repository.read(CONTROLLER_MAILBOX).events) == 1

        receipt = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=_checkpoint(),
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T05:03:31Z",
            committed_at="2026-10-07T05:03:32Z",
        )
    finally:
        ledger.close()

    assert len(repository.read(CONTROLLER_MAILBOX).events) == 1
    assert receipt.dispatch.committed.readback_verified is True
    assert receipt.event_remote.payload["event_id"] == receipt.dispatch.committed.event_id


def test_crash_after_event_before_materializer_completion_recovers_without_duplicate_event(
    tmp_path: Path,
) -> None:
    transport, repository, continuation, base_ledger = _runtime(tmp_path)
    crash_ledger = CrashAfterLedgerCommit(base_ledger)
    with pytest.raises(RuntimeError, match="synthetic crash after ledger commit"):
        materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=crash_ledger,
            checkpoint=_checkpoint(),
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T05:04:01Z",
            committed_at="2026-10-07T05:04:02Z",
        )

    receipt = materialize_controller_transition(
        continuation_store=continuation,
        repository=repository,
        ledger=crash_ledger,
        checkpoint=_checkpoint(),
        request=_request(),
        state_version=0,
        prepared_at="2026-10-07T05:04:01Z",
        committed_at="2026-10-07T05:04:02Z",
    )
    base_ledger.close()

    records = [json.loads(comment.body) for comment in transport.comments]
    assert sum(
        record.get("record_type") == "event"
        for record in records
        if record.get("protocol") == GITHUB_RECORD_PROTOCOL
    ) == 1
    assert receipt.dispatch.committed.readback_verified is True


def test_crash_after_cursor_before_continuation_readback_retries_idempotently(
    tmp_path: Path,
) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    crashing_store = CrashBeforeContinuationReadback(continuation)
    try:
        with pytest.raises(RuntimeError, match="post-cursor continuation readback"):
            materialize_controller_transition(
                continuation_store=crashing_store,
                repository=repository,
                ledger=ledger,
                checkpoint=_checkpoint(),
                request=_request(),
                state_version=0,
                prepared_at="2026-10-07T05:05:01Z",
                committed_at="2026-10-07T05:05:02Z",
            )

        receipt = materialize_controller_transition(
            continuation_store=crashing_store,
            repository=repository,
            ledger=ledger,
            checkpoint=_checkpoint(),
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T05:05:01Z",
            committed_at="2026-10-07T05:05:02Z",
        )
    finally:
        ledger.close()

    records = [json.loads(comment.body) for comment in transport.comments]
    assert sum(
        record.get("record_type") == "event"
        for record in records
        if record.get("protocol") == GITHUB_RECORD_PROTOCOL
    ) == 1
    assert sum(
        record.get("record_type") == "cursor"
        for record in records
        if record.get("protocol") == GITHUB_RECORD_PROTOCOL
    ) == 1
    assert receipt.dispatch.cursor.last_event_seq == 0

def test_resume_breaks_wait_executor_loop_when_execution_attempt_expired(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        materialized = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:46:00Z",
            committed_at="2026-10-07T04:46:01Z",
        )
        cursor = MailboxActorCursor.initial(
            EXECUTOR_MAILBOX,
            run_id=materialized.envelope.run_id,
            node_id=materialized.envelope.node_id,
            actor_namespace="hermes-executor",
        )

        resumed = resume_controller_v2(
            continuation_store=continuation,
            repository=repository,
            checkpoint=checkpoint,
            cursor=cursor,
            correlation_id=materialized.envelope.to_dict()["correlation_id"],
            expected_identity=materialized.envelope.execution_identity,
            observed_at="2026-10-07T05:46:00Z",
        )
    finally:
        ledger.close()

    assert resumed.poll.status == "NO_NEW_RESULT"
    assert resumed.checkpoint.phase == ContinuationPhase.WAIT_CONTROLLER.value
    assert resumed.checkpoint.next_action == WAIT_EXECUTOR_AUTHORITY_ACTION
    assert resumed.checkpoint.last_seen_executor_seq == checkpoint.last_seen_executor_seq
    assert resumed.checkpoint.expected_executor_seq == checkpoint.expected_executor_seq


def test_resume_explicit_missing_active_lease_breaks_wait_executor_before_expiry(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        materialized = materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:46:00Z",
            committed_at="2026-10-07T04:46:01Z",
        )
        cursor = MailboxActorCursor.initial(
            EXECUTOR_MAILBOX,
            run_id=materialized.envelope.run_id,
            node_id=materialized.envelope.node_id,
            actor_namespace="hermes-executor",
        )

        resumed = resume_controller_v2(
            continuation_store=continuation,
            repository=repository,
            checkpoint=checkpoint,
            cursor=cursor,
            correlation_id=materialized.envelope.to_dict()["correlation_id"],
            expected_identity=materialized.envelope.execution_identity,
            observed_at="2026-10-07T05:00:00Z",
            active_lease=None,
        )
    finally:
        ledger.close()

    assert resumed.checkpoint.phase == ContinuationPhase.WAIT_CONTROLLER.value
    assert resumed.checkpoint.next_action == WAIT_EXECUTOR_AUTHORITY_ACTION


def test_recovery_breaks_wait_executor_loop_when_execution_attempt_expired(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:46:00Z",
            committed_at="2026-10-07T04:46:01Z",
        )
    finally:
        ledger.close()

    restarted_repository = GitHubMailboxRepository(transport)
    restarted_continuation = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )
    recovered = recover_high_integrity_session(
        continuation_store=restarted_continuation,
        repository=restarted_repository,
        run_id=checkpoint.run_id,
        observed_at="2026-10-07T05:46:00Z",
    )

    assert recovered.checkpoint.phase == ContinuationPhase.WAIT_CONTROLLER.value
    assert recovered.checkpoint.next_action == WAIT_EXECUTOR_AUTHORITY_ACTION


def test_wait_executor_recovery_requires_observed_time(tmp_path: Path) -> None:
    transport, repository, continuation, ledger = _runtime(tmp_path)
    checkpoint = _checkpoint()
    try:
        materialize_controller_transition(
            continuation_store=continuation,
            repository=repository,
            ledger=ledger,
            checkpoint=checkpoint,
            request=_request(),
            state_version=0,
            prepared_at="2026-10-07T04:46:00Z",
            committed_at="2026-10-07T04:46:01Z",
        )
    finally:
        ledger.close()

    restarted_repository = GitHubMailboxRepository(transport)
    restarted_continuation = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )
    with pytest.raises(TaskControllerValidationError, match="RECOVERY_TIME_REQUIRED"):
        recover_high_integrity_session(
            continuation_store=restarted_continuation,
            repository=restarted_repository,
            run_id=checkpoint.run_id,
        )
\n