"""TC-MBX-601 hardening: isolated first-pass reviewer sessions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from taskcontroller.standards import StandardsProfile, StandardsResolver, StandardsSourceRef
from taskcontroller.standards.context_pack import ContextPackBuilder
from taskcontroller.standards.reviewer_session import (
    ReviewerSessionError,
    ReviewerSessionFactory,
    ReviewerSpec,
)


_COMMIT = "d" * 40


class SourceReader:
    def __init__(self, values: dict[tuple[str, str], bytes]) -> None:
        self.values = values

    def read_exact(self, source: StandardsSourceRef) -> bytes:
        return self.values[(source.commit_sha, source.path)]


def _source(commit: str, path: str, content: str) -> StandardsSourceRef:
    return StandardsSourceRef(
        repository="owner-repo",
        commit_sha=commit,
        path=path,
        blob_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
    )


def _task_context_pack():
    standards_source = _source(_COMMIT, "standards/AGENTS.md", "shared standards")
    standards_reader = SourceReader({(_COMMIT, standards_source.path): b"shared standards"})
    profile = StandardsProfile.create(
        profile_id="taskcontroller.engineering",
        version="v1",
        sources=(standards_source,),
    )
    standards = StandardsResolver(standards_reader).resolve(profile).session_context

    task_source = _source(_COMMIT, "src/task.py", "bound task source")
    task_reader = SourceReader({(_COMMIT, task_source.path): b"bound task source"})
    return ContextPackBuilder(task_reader).build(
        source_refs=(task_source,),
        evidence_refs=(),
        standards=standards,
    )


def _reviewers() -> tuple[ReviewerSpec, ...]:
    return (
        ReviewerSpec(reviewer_id="reviewer-a", lens="architecture"),
        ReviewerSpec(reviewer_id="reviewer-b", lens="security"),
    )


def test_first_pass_sessions_have_distinct_ids_and_bound_source_standards() -> None:
    pack = _task_context_pack()
    sessions = ReviewerSessionFactory().create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=pack,
        reviewers=_reviewers(),
    )

    assert len(sessions) == 2
    assert len({session.session_id for session in sessions}) == 2
    assert len({session.context_id for session in sessions}) == 2
    assert all(session.phase == "INITIAL_FIRST_PASS" for session in sessions)
    assert all(session.source_pack_digest == pack.inventory_digest for session in sessions)
    assert all(
        session.standards_profile_digest == pack.standards.receipt.digest
        for session in sessions
    )
    assert all(
        session.standards_context_digest == pack.standards.receipt.context_digest
        for session in sessions
    )
    assert all(session.peer_finding_refs == () for session in sessions)

    for session in sessions:
        payload = session.first_pass_context()
        assert payload["session_id"] == session.session_id
        assert payload["context_id"] == session.context_id
        assert payload["source_binding"]["inventory_digest"] == pack.inventory_digest
        assert payload["standards_binding"]["profile_digest"] == pack.standards.receipt.digest
        assert payload["peer_finding_refs"] == []
        assert "peer_findings" not in payload
        assert "peer_conclusions" not in payload
        assert "findings" not in payload


def test_first_pass_context_never_contains_peer_ids_claims_or_history() -> None:
    pack = _task_context_pack()
    sessions = ReviewerSessionFactory().create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=pack,
        reviewers=_reviewers(),
    )
    payloads = [json.dumps(session.first_pass_context(), sort_keys=True) for session in sessions]

    assert all("finding-from-reviewer-a" not in payload for payload in payloads)
    assert all("peer conclusion" not in payload for payload in payloads)
    assert all("slack" not in payload.lower() for payload in payloads)
    assert all("gpt" not in payload.lower() for payload in payloads)


def test_session_allocation_is_deterministic_under_reviewer_input_reordering() -> None:
    pack = _task_context_pack()
    factory = ReviewerSessionFactory()
    forward = factory.create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=pack,
        reviewers=_reviewers(),
    )
    reverse = factory.create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=pack,
        reviewers=tuple(reversed(_reviewers())),
    )

    assert [session.to_dict() for session in forward] == [
        session.to_dict() for session in reverse
    ]


def test_first_pass_context_is_defensive_and_digest_bound() -> None:
    pack = _task_context_pack()
    session = ReviewerSessionFactory().create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=pack,
        reviewers=(ReviewerSpec(reviewer_id="reviewer-a", lens="architecture"),),
    )[0]
    payload = session.first_pass_context()
    payload["source_binding"]["refs"].clear()
    payload["standards_binding"]["source_refs"].clear()

    restored = session.first_pass_context()
    assert restored["source_binding"]["refs"]
    assert restored["standards_binding"]["source_refs"]
    assert session.session_digest == session.to_dict()["session_digest"]


def test_peer_injection_is_rejected_before_session_creation() -> None:
    with pytest.raises(ReviewerSessionError) as caught:
        ReviewerSessionFactory().create(
            run_id="run-1",
            node_id="node-1",
            attempt_id="attempt-1",
            task_context=_task_context_pack(),
            reviewers=_reviewers(),
            peer_finding_refs=("finding-a",),
        )

    assert caught.value.code == "REVIEWER_PEER_INPUT_FORBIDDEN"


def test_peer_fields_in_reviewer_spec_are_rejected() -> None:
    with pytest.raises(ReviewerSessionError) as caught:
        ReviewerSessionFactory().create(
            run_id="run-1",
            node_id="node-1",
            attempt_id="attempt-1",
            task_context=_task_context_pack(),
            reviewers=(
                {
                    "reviewer_id": "reviewer-a",
                    "lens": "architecture",
                    "peer_findings": ["finding-from-peer"],
                },
            ),
        )

    assert caught.value.code == "REVIEWER_PEER_INPUT_FORBIDDEN"


def test_duplicate_reviewer_identity_is_rejected() -> None:
    with pytest.raises(ReviewerSessionError) as caught:
        ReviewerSessionFactory().create(
            run_id="run-1",
            node_id="node-1",
            attempt_id="attempt-1",
            task_context=_task_context_pack(),
            reviewers=(
                ReviewerSpec(reviewer_id="reviewer-a", lens="architecture"),
                ReviewerSpec(reviewer_id="reviewer-a", lens="security"),
            ),
        )

    assert caught.value.code == "REVIEWER_IDENTITY_COLLISION"


def test_malformed_context_and_spec_fail_closed() -> None:
    with pytest.raises(ReviewerSessionError) as context_error:
        ReviewerSessionFactory().create(
            run_id="run-1",
            node_id="node-1",
            attempt_id="attempt-1",
            task_context=None,
            reviewers=_reviewers(),
        )
    assert context_error.value.code == "REVIEWER_CONTEXT_INVALID"

    with pytest.raises(ReviewerSessionError) as spec_error:
        ReviewerSessionFactory().create(
            run_id="run-1",
            node_id="node-1",
            attempt_id="attempt-1",
            task_context=_task_context_pack(),
            reviewers=({"reviewer_id": "reviewer-a"},),
        )
    assert spec_error.value.code == "REVIEWER_SPEC_INVALID"


def test_session_payload_contains_no_raw_subagent_chat_fields() -> None:
    pack = _task_context_pack()
    session = ReviewerSessionFactory().create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=pack,
        reviewers=_reviewers(),
    )[0]
    payload: dict[str, Any] = session.to_dict()
    serialized = json.dumps(payload, sort_keys=True)

    assert "raw_output" not in serialized
    assert "transcript" not in serialized
    assert "conversation_history" not in serialized
    assert payload["source_binding"]["refs"]
    assert payload["standards_binding"]["source_refs"]
