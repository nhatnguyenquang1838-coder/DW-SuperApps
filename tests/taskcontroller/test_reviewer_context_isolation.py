"""TC-MBX-601: independent reviewer initial-context isolation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from taskcontroller.standards import StandardsProfile, StandardsResolver, StandardsSourceRef
from taskcontroller.standards.context_pack import ContextPackBuilder
from taskcontroller.standards.reviewer_context import (
    ReviewerContextError,
    ReviewerInitialContextFactory,
)


_COMMIT = "c" * 40


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


def _finding(reviewer: str, finding_id: str, claim: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "reviewer": reviewer,
        "severity": "major",
        "claim": claim,
        "evidence_refs": [f"evidence://{finding_id}"],
    }


def test_initial_contexts_are_independent_and_exclude_peer_findings() -> None:
    pack = _task_context_pack()
    finding_a = _finding("reviewer-a", "finding-a", "A-only finding claim")
    finding_b = _finding("reviewer-b", "finding-b", "B-only finding claim")
    factory = ReviewerInitialContextFactory()

    context_a = factory.build(
        reviewer_id="reviewer-a",
        lens="architecture",
        task_context=pack,
        own_findings=(finding_a,),
    )
    context_b = factory.build(
        reviewer_id="reviewer-b",
        lens="security",
        task_context=pack,
        own_findings=(finding_b,),
    )

    payload_a = json.dumps(context_a.first_prompt_context(), sort_keys=True)
    payload_b = json.dumps(context_b.first_prompt_context(), sort_keys=True)

    assert finding_a["finding_id"] in payload_a
    assert finding_b["finding_id"] in payload_b
    assert finding_a["finding_id"] not in payload_b
    assert finding_a["claim"] not in payload_b
    assert finding_b["finding_id"] not in payload_a
    assert finding_b["claim"] not in payload_a
    assert context_a.task_context.inventory == context_b.task_context.inventory
    assert context_a.context_digest != context_b.context_digest
    assert "peer_findings" not in context_b.first_prompt_context()


def test_foreign_finding_cannot_be_injected_into_a_reviewers_initial_context() -> None:
    finding_a = _finding("reviewer-a", "finding-a", "A-only finding claim")

    with pytest.raises(ReviewerContextError) as caught:
        ReviewerInitialContextFactory().build(
            reviewer_id="reviewer-b",
            lens="testing",
            task_context=_task_context_pack(),
            own_findings=(finding_a,),
        )

    assert caught.value.code == "REVIEWER_FINDING_OWNER_MISMATCH"


def test_initial_context_payload_is_defensive_and_reproducible() -> None:
    pack = _task_context_pack()
    factory = ReviewerInitialContextFactory()
    first = factory.build(
        reviewer_id="reviewer-a",
        lens="architecture",
        task_context=pack,
        own_findings=(_finding("reviewer-a", "finding-a", "A-only finding claim"),),
    )
    second = factory.build(
        reviewer_id="reviewer-a",
        lens="architecture",
        task_context=pack,
        own_findings=(_finding("reviewer-a", "finding-a", "A-only finding claim"),),
    )

    payload = first.first_prompt_context()
    payload["own_findings"].clear()

    assert first.first_prompt_context()["own_findings"]
    assert first.context_digest == second.context_digest
    assert first.first_prompt_context() == second.first_prompt_context()
