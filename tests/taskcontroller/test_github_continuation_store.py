from __future__ import annotations

import json
from dataclasses import replace

import pytest

from taskcontroller.audit.manifest import RunManifest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.continuation import (
    CONTINUATION_MANIFEST_KIND,
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
    persist_before_dispatch,
    recover_continuation,
)
from taskcontroller.interaction.github_continuation_store import (
    GITHUB_CONTINUATION_RECORD_PROTOCOL,
    GitHubContinuationStore,
)
from taskcontroller.interaction.github_mailbox_v2 import (
    GitHubIssueComment,
    GitHubIssueCommentTransport,
)


REPOSITORY = "nhatnguyenquang1838-coder/gwc"
ISSUE = 575
RUN = "scrum781-q0-20260920T074727Z"


class FakeGitHubComments:
    def __init__(self) -> None:
        self.comments: list[GitHubIssueComment] = []
        self.next_id = 2000
        self.calls: list[tuple[str, str, int]] = []

    def list_comments(self, repository: str, issue_number: int):
        self.calls.append(("list", repository, issue_number))
        return tuple(self.comments)

    def create_comment(self, repository: str, issue_number: int, body: str):
        self.calls.append(("create", repository, issue_number))
        comment = GitHubIssueComment(str(self.next_id), body)
        self.next_id += 1
        self.comments.append(comment)
        return comment

    def append_foreign(self, body: str) -> None:
        self.comments.append(GitHubIssueComment(str(self.next_id), body))
        self.next_id += 1

    def replace_body(self, comment_id: str, body: str) -> None:
        self.comments = [
            GitHubIssueComment(item.comment_id, body)
            if item.comment_id == comment_id
            else item
            for item in self.comments
        ]


class CorruptingTransport(FakeGitHubComments):
    def create_comment(self, repository: str, issue_number: int, body: str):
        created = super().create_comment(repository, issue_number, body)
        parsed = json.loads(created.body)
        parsed["manifest_digest"] = "sha256:" + "0" * 64
        self.replace_body(
            created.comment_id,
            json.dumps(parsed, sort_keys=True, separators=(",", ":")),
        )
        return created


def _store(transport=None) -> tuple[GitHubContinuationStore, FakeGitHubComments]:
    backend = transport or FakeGitHubComments()
    return (
        GitHubContinuationStore(
            backend,
            repository=REPOSITORY,
            issue_number=ISSUE,
        ),
        backend,
    )


def _checkpoint(**changes) -> ControllerContinuation:
    values = {
        "run_id": RUN,
        "controller_epoch": 1,
        "phase": ContinuationPhase.WAIT_EXECUTOR.value,
        "status": ContinuationStatus.ACTIVE.value,
        "next_action": "POLL_EXECUTOR",
        "controller_mailbox_ref": f"github://{REPOSITORY}/issues/{ISSUE}#scrum781-controller-v2",
        "controller_seq": 1,
        "executor_actor": "hermes-cloud",
        "executor_mailbox_ref": f"github://{REPOSITORY}/issues/{ISSUE}#scrum781-executor-v2",
        "expected_executor_seq": 1,
        "last_seen_executor_seq": 0,
        "wakeup_binding": "slack-websocket",
        "exact_head_sha": "8677d141ffceb7bbaa87bc4d163a8546a4e4287a",
        "updated_at": "2026-10-05T15:20:00Z",
    }
    values.update(changes)
    return ControllerContinuation(**values)


def _other_manifest(**changes) -> RunManifest:
    values = {
        "run_id": "other-run",
        "manifest_kind": "custom-kind",
        "schema_version": "1",
        "created_at": "2026-10-05T15:20:00Z",
        "updated_at": "2026-10-05T15:20:00Z",
        "metadata": {"value": 1},
    }
    values.update(changes)
    return RunManifest(**values)


def test_transport_protocol_and_store_capabilities() -> None:
    store, transport = _store()

    assert isinstance(transport, GitHubIssueCommentTransport)
    caps = store.capabilities()
    assert caps["protocol"] == GITHUB_CONTINUATION_RECORD_PROTOCOL
    assert caps["adapter"] == "github_issue_comments"
    assert caps["append_only"] is True
    assert caps["single_writer_required"] is True
    assert caps["cross_process_multi_writer_cas"] is False


def test_first_save_and_load_round_trip_exact_manifest() -> None:
    store, transport = _store()
    manifest = _checkpoint().to_manifest()

    store.save_manifest(manifest)
    recovered = store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND)

    assert recovered == manifest
    assert len(transport.comments) == 1
    record = json.loads(transport.comments[0].body)
    assert record["protocol"] == GITHUB_CONTINUATION_RECORD_PROTOCOL
    assert record["record_seq"] == 0
    assert record["previous_record_digest"] is None
    assert record["manifest"]["run_id"] == RUN


def test_persist_before_dispatch_round_trips_through_github_store() -> None:
    store, _ = _store()
    checkpoint = _checkpoint()

    persisted = persist_before_dispatch(store, checkpoint)
    recovered = recover_continuation(store, RUN)

    assert persisted == checkpoint
    assert recovered == checkpoint
    assert recovered is not None
    assert recovered.checkpoint_id == checkpoint.checkpoint_id


def test_exact_duplicate_save_is_idempotent() -> None:
    store, transport = _store()
    manifest = _checkpoint().to_manifest()

    store.save_manifest(manifest)
    store.save_manifest(manifest)

    assert len(transport.comments) == 1
    assert store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND) == manifest


def test_changed_checkpoint_appends_monotonic_digest_chain() -> None:
    store, transport = _store()
    first = _checkpoint().to_manifest()
    store.save_manifest(first)
    second_checkpoint = _checkpoint(
        controller_seq=2,
        expected_executor_seq=2,
        last_seen_executor_seq=1,
        updated_at="2026-10-05T15:21:00Z",
    )
    second = second_checkpoint.to_manifest(created_at=first.created_at)

    store.save_manifest(second)

    assert store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND) == second
    assert len(transport.comments) == 2
    one = json.loads(transport.comments[0].body)
    two = json.loads(transport.comments[1].body)
    assert one["record_seq"] == 0
    assert two["record_seq"] == 1
    assert two["previous_record_digest"] == one["digest"]


def test_changed_manifest_rejects_created_at_change() -> None:
    store, _ = _store()
    first = _checkpoint().to_manifest()
    store.save_manifest(first)
    changed = replace(
        first,
        created_at="2026-10-05T15:20:30Z",
        updated_at="2026-10-05T15:21:00Z",
        metadata={**first.metadata, "controller_seq": 2},
    )

    with pytest.raises(TaskControllerValidationError, match="created_at"):
        store.save_manifest(changed)


def test_changed_manifest_requires_updated_at_to_move_forward() -> None:
    store, _ = _store()
    first = _checkpoint().to_manifest()
    store.save_manifest(first)
    changed = replace(
        first,
        metadata={**first.metadata, "controller_seq": 2},
    )

    with pytest.raises(TaskControllerValidationError, match="strictly forward"):
        store.save_manifest(changed)


def test_foreign_comments_and_other_run_kind_are_ignored() -> None:
    store, transport = _store()
    transport.append_foreign("human issue discussion")
    transport.append_foreign('{"protocol":"other","payload":{}}')
    store.save_manifest(_other_manifest())
    manifest = _checkpoint().to_manifest()
    store.save_manifest(manifest)

    assert store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND) == manifest
    assert store.load_manifest("other-run", "custom-kind") == _other_manifest()


def test_malformed_tagged_record_fails_closed() -> None:
    store, transport = _store()
    transport.append_foreign(
        '{"protocol":"dw.taskcontroller.github-continuation-record/v1","run_id":'
    )

    with pytest.raises(TaskControllerValidationError, match="not valid JSON"):
        store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND)


def test_manifest_tamper_is_detected() -> None:
    store, transport = _store()
    store.save_manifest(_checkpoint().to_manifest())
    record = json.loads(transport.comments[0].body)
    record["manifest"]["metadata"]["controller_seq"] = 99
    transport.replace_body(
        transport.comments[0].comment_id,
        json.dumps(record, sort_keys=True, separators=(",", ":")),
    )

    with pytest.raises(TaskControllerValidationError, match="manifest digest mismatch"):
        store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND)


def test_record_chain_tamper_is_detected() -> None:
    store, transport = _store()
    first = _checkpoint().to_manifest()
    store.save_manifest(first)
    second = _checkpoint(
        controller_seq=2,
        expected_executor_seq=2,
        last_seen_executor_seq=1,
        updated_at="2026-10-05T15:21:00Z",
    ).to_manifest(created_at=first.created_at)
    store.save_manifest(second)
    record = json.loads(transport.comments[1].body)
    record["previous_record_digest"] = "sha256:" + "f" * 64
    unsigned = {key: value for key, value in record.items() if key != "digest"}
    from taskcontroller.interaction.mailbox_v2 import canonical_digest
    record["digest"] = canonical_digest(unsigned)
    transport.replace_body(
        transport.comments[1].comment_id,
        json.dumps(record, sort_keys=True, separators=(",", ":")),
    )

    with pytest.raises(TaskControllerValidationError, match="digest chain"):
        store.load_manifest(RUN, CONTINUATION_MANIFEST_KIND)


def test_corrupted_exact_readback_fails_save() -> None:
    transport = CorruptingTransport()
    store = GitHubContinuationStore(
        transport,
        repository=REPOSITORY,
        issue_number=ISSUE,
    )

    with pytest.raises(TaskControllerValidationError, match="manifest digest mismatch"):
        store.save_manifest(_checkpoint().to_manifest())


def test_invalid_constructor_binding_fails_closed() -> None:
    transport = FakeGitHubComments()

    with pytest.raises(TaskControllerValidationError):
        GitHubContinuationStore(transport, repository="", issue_number=ISSUE)
    with pytest.raises(TaskControllerValidationError):
        GitHubContinuationStore(transport, repository=REPOSITORY, issue_number=0)
