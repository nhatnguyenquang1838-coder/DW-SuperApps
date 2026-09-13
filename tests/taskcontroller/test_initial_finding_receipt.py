"""TC-MBX-602 hardening: immutable initial-finding receipts."""

from __future__ import annotations

import hashlib
import json

import pytest

from taskcontroller.execution.initial_finding_receipt import (
    InitialFindingReceiptError,
    InitialFindingReceiptLedger,
    create_initial_finding_receipt,
    digest_findings,
)
from taskcontroller.standards import StandardsProfile, StandardsResolver, StandardsSourceRef
from taskcontroller.standards.context_pack import ContextPackBuilder
from taskcontroller.standards.reviewer_session import ReviewerSessionFactory, ReviewerSpec


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
    standards = StandardsResolver(
        SourceReader({(_COMMIT, standards_source.path): b"shared standards"})
    ).resolve(
        StandardsProfile.create(
            profile_id="taskcontroller.engineering",
            version="v1",
            sources=(standards_source,),
        )
    ).session_context
    task_source = _source(_COMMIT, "src/task.py", "bound task source")
    return ContextPackBuilder(
        SourceReader({(_COMMIT, task_source.path): b"bound task source"})
    ).build(
        source_refs=(task_source,),
        evidence_refs=(),
        standards=standards,
    )


def _sessions():
    return ReviewerSessionFactory().create(
        run_id="run-1",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=_task_context_pack(),
        reviewers=(
            ReviewerSpec(reviewer_id="reviewer-a", lens="architecture"),
            ReviewerSpec(reviewer_id="reviewer-b", lens="security"),
        ),
    )


def _finding(finding_id: str, severity: str = "major") -> dict[str, str]:
    return {
        "finding_id": finding_id,
        "reviewer": "reviewer-a",
        "severity": severity,
        "summary": f"summary-{finding_id}",
    }


def _receipt(session, findings=None, recorded_at="2026-09-12T16:20:00Z"):
    return create_initial_finding_receipt(
        session=session,
        findings=findings or (_finding("finding-a"),),
        recorded_at=recorded_at,
    )


def test_receipt_binds_reviewer_context_source_standards_finding_and_timestamp() -> None:
    session = _sessions()[0]
    receipt = _receipt(session)

    payload = receipt.to_dict()
    assert payload["reviewer_id"] == session.reviewer_id
    assert payload["session_id"] == session.session_id
    assert payload["context_id"] == session.context_id
    assert payload["run_id"] == session.run_id
    assert payload["node_id"] == session.node_id
    assert payload["attempt_id"] == session.attempt_id
    assert payload["source_digest"] == session.source_pack_digest
    assert payload["standards_profile_digest"] == session.standards_profile_digest
    assert payload["standards_context_digest"] == session.standards_context_digest
    assert payload["finding_digest"] == digest_findings((_finding("finding-a"),))
    assert payload["recorded_at"] == "2026-09-12T16:20:00Z"
    assert payload["receipt_digest"].startswith("sha256:")
    assert "summary-finding-a" not in json.dumps(payload, sort_keys=True)
    assert "transcript" not in json.dumps(payload, sort_keys=True)


def test_finding_digest_and_receipt_are_deterministic_under_finding_reordering() -> None:
    session = _sessions()[0]
    findings = (_finding("finding-b"), _finding("finding-a", "critical"))
    reordered = tuple(reversed(findings))

    first = _receipt(session, findings=findings)
    second = _receipt(session, findings=reordered)

    assert first.finding_digest == second.finding_digest
    assert first.receipt_digest == second.receipt_digest
    assert first.to_dict() == second.to_dict()


def test_receipt_rejects_naive_timestamp_and_malformed_finding_input() -> None:
    session = _sessions()[0]
    with pytest.raises(InitialFindingReceiptError) as timestamp_error:
        _receipt(session, recorded_at="2026-09-12T16:20:00")
    assert timestamp_error.value.code == "RECEIPT_TIMESTAMP_INVALID"

    with pytest.raises(InitialFindingReceiptError) as findings_error:
        _receipt(session, findings=("raw finding text",))
    assert findings_error.value.code == "RECEIPT_FINDINGS_INVALID"


def test_ledger_waits_for_every_required_receipt_before_cross_review() -> None:
    sessions = _sessions()
    ledger = InitialFindingReceiptLedger.from_sessions(sessions)

    assert ledger.required_reviewer_ids == ("reviewer-a", "reviewer-b")
    assert ledger.missing_reviewer_ids == ("reviewer-a", "reviewer-b")
    assert ledger.ready_for_cross_review is False
    with pytest.raises(InitialFindingReceiptError) as blocked:
        ledger.require_cross_review_ready()
    assert blocked.value.code == "INITIAL_RECEIPTS_INCOMPLETE"

    ledger = ledger.append(_receipt(sessions[0]))
    assert ledger.missing_reviewer_ids == ("reviewer-b",)
    assert ledger.ready_for_cross_review is False

    reviewer_b_finding = {
        "finding_id": "finding-b",
        "reviewer": "reviewer-b",
        "severity": "minor",
        "summary": "summary-finding-b",
    }
    ledger = ledger.append(_receipt(sessions[1], findings=(reviewer_b_finding,)))
    assert ledger.missing_reviewer_ids == ()
    assert ledger.ready_for_cross_review is True
    assert ledger.require_cross_review_ready() == ledger
    sealed = ledger.seal()
    assert sealed.sealed is True
    assert sealed.to_dict()["ready_for_cross_review"] is True


def test_ledger_rejects_foreign_or_mismatched_receipt_binding() -> None:
    sessions = _sessions()
    ledger = InitialFindingReceiptLedger.from_sessions(sessions)
    foreign_session = ReviewerSessionFactory().create(
        run_id="foreign-run",
        node_id="node-1",
        attempt_id="attempt-1",
        task_context=_task_context_pack(),
        reviewers=(ReviewerSpec(reviewer_id="reviewer-a", lens="architecture"),),
    )[0]

    with pytest.raises(InitialFindingReceiptError) as caught:
        ledger.append(_receipt(foreign_session))
    assert caught.value.code == "RECEIPT_BINDING_MISMATCH"


def test_identical_duplicate_is_idempotent_but_conflicting_duplicate_is_rejected() -> None:
    session = _sessions()[0]
    ledger = InitialFindingReceiptLedger.from_sessions(_sessions())
    receipt = _receipt(session)
    once = ledger.append(receipt)
    twice = once.append(receipt)
    assert twice == once

    conflicting = _receipt(
        session,
        findings=(_finding("different-finding", "critical"),),
    )
    with pytest.raises(InitialFindingReceiptError) as caught:
        once.append(conflicting)
    assert caught.value.code == "RECEIPT_DUPLICATE_CONFLICT"


def test_ledger_snapshot_is_immutable_and_manifest_digest_is_stable() -> None:
    sessions = _sessions()
    ledger = InitialFindingReceiptLedger.from_sessions(sessions)
    ledger = ledger.append(_receipt(sessions[0]))
    payload = ledger.to_dict()
    payload["receipts"].clear()

    restored = ledger.to_dict()
    assert restored["receipts"]
    assert ledger.manifest_digest == ledger.to_dict()["manifest_digest"]
    assert ledger.to_dict() == InitialFindingReceiptLedger.from_dict(ledger.to_dict()).to_dict()


def test_sealed_ledger_rejects_late_receipts() -> None:
    sessions = _sessions()
    ledger = InitialFindingReceiptLedger.from_sessions(sessions)
    ledger = ledger.append(_receipt(sessions[0]))
    ledger = ledger.append(
        _receipt(
            sessions[1],
            findings=(
                {
                    "finding_id": "finding-b",
                    "reviewer": "reviewer-b",
                    "severity": "minor",
                    "summary": "summary-finding-b",
                },
            ),
        )
    ).seal()

    with pytest.raises(InitialFindingReceiptError) as caught:
        ledger.append(_receipt(sessions[0]))
    assert caught.value.code == "RECEIPT_LEDGER_SEALED"
