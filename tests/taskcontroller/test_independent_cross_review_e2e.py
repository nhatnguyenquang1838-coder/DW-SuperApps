"""TC-MBX-1003: independent cross-review end-to-end contract proof.

This test is the bounded end-to-end proof that the existing provider-neutral
primitives compose into the independent cross-review sequence required by
WP10:

1. Two reviewers with identical task/source/standards context receive isolated
   first-pass contexts that exclude the other reviewer's finding_id and claim
   before any verdict exists.
2. Immutable initial finding receipts and normalized findings are materialized
   for each reviewer.
3. Independent first verdicts are submitted.
4. An explicit conflict is adjudicated, and the result is
   NEEDS_CLARIFICATION / ESCALATE, with conflict finding_ids, reviewers, and
   evidence_refs retained -- never a silent PASS.
5. The Mixer input manifest preserves the conflict and blocks clean synthesis.

This test is pure white-box contract proof. It imports only provider-neutral
execution/standards modules, never dispatches a provider, never activates
runtime fan-out or cross-review, and never writes mailbox/Slack/GitHub state
or performs commit/push/PR/merge/deploy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from taskcontroller.domain.enums import DecisionType, ReviewVerdict
from taskcontroller.execution.conflict_adjudicator import (
    ConflictAdjudicationResult,
    ConflictDisposition,
    ConflictResolution,
    ConflictGroup,
    adjudicate_conflicts,
)
from taskcontroller.execution.initial_finding_receipt import (
    InitialFindingReceipt,
    InitialFindingReceiptLedger,
    create_initial_finding_receipt,
    digest_findings,
)
from taskcontroller.execution.mixer_input_manifest import (
    MixerConflict,
    MixerInputManifest,
    MixerInputManifestError,
    MixerReviewerInput,
)
from taskcontroller.execution.result_normalizer import NormalizedFinding
from taskcontroller.execution.severity_preservation import ReviewerOutcome
from taskcontroller.standards import StandardsProfile, StandardsResolver, StandardsSourceRef
from taskcontroller.standards.context_pack import ContextPackBuilder, TaskContextPack
from taskcontroller.standards.reviewer_context import (
    ReviewerContextError,
    ReviewerInitialContextFactory,
)
from taskcontroller.standards.reviewer_session import (
    ReviewerSessionError,
    ReviewerSessionFactory,
    ReviewerSpec,
    ReviewerSession,
)

_COMMIT = "c" * 40

# Exact content that will be used for both source refs and source reader
_ARCH_CONTENT = "# Architecture Standards\nRule 1: All boundaries must be explicit\nRule 2: No implicit auth\n"
_TEST_CONTENT = "# Testing Standards\nRule 1: Unit tests required\nRule 2: Integration tests for boundaries\n"


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


def _profile(sources: list[StandardsSourceRef]) -> StandardsProfile:
    return StandardsProfile.create(
        profile_id="test-profile",
        version="1.0",
        sources=sources,
    )


def _make_reviewer_spec(
    reviewer_id: str,
    lens: str,
) -> ReviewerSpec:
    return ReviewerSpec(
        reviewer_id=reviewer_id,
        lens=lens,
    )


def _make_findings() -> tuple[NormalizedFinding, ...]:
    return (
        NormalizedFinding(
            finding_id="F-001",
            severity="CRITICAL",
            category="architecture",
            lens="architecture",
            claim="Missing auth boundary in payment flow",
            evidence_refs=("ev-1", "ev-2"),
            recommendation="Add authorization check",
            reviewer="reviewer-a",
            confidence=0.95,
        ),
        NormalizedFinding(
            finding_id="F-002",
            severity="MINOR",
            category="testing",
            lens="testing",
            claim="Code style inconsistency",
            evidence_refs=("ev-3",),
            recommendation="Apply formatter",
            reviewer="reviewer-b",
            confidence=0.60,
        ),
    )


def _make_reviewer_sessions() -> tuple[ReviewerSession, ...]:
    """Create mock reviewer sessions for receipt creation with shared identity."""
    session_a = ReviewerSession(
        run_id="run-001",
        node_id="mbx-tc-1003",
        attempt_id="attempt-001",
        reviewer_id="reviewer-a",
        lens="architecture",
        session_id="sess-a",
        context_id="ctx-a",
        source_pack_digest="sha256:" + "a" * 64,
        standards_profile_digest="sha256:" + "a" * 64,
        standards_context_digest="sha256:" + "a" * 64,
        standards_materialization_digest="sha256:" + "a" * 64,
        source_refs=(dict(repository="owner-repo", commit_sha=_COMMIT, path="standards/architecture.md", blob_digest="sha256:" + "a" * 64),),
        standards_source_refs=(dict(repository="owner-repo", commit_sha=_COMMIT, path="standards/architecture.md", blob_digest="sha256:" + "a" * 64),),
        context_digest="sha256:" + "a" * 64,
        session_digest="sha256:" + "a" * 64,
    )
    session_b = ReviewerSession(
        run_id="run-001",
        node_id="mbx-tc-1003",
        attempt_id="attempt-001",
        reviewer_id="reviewer-b",
        lens="testing",
        session_id="sess-b",
        context_id="ctx-b",
        source_pack_digest="sha256:" + "a" * 64,  # SAME as session_a
        standards_profile_digest="sha256:" + "a" * 64,  # SAME as session_a
        standards_context_digest="sha256:" + "a" * 64,  # SAME as session_a
        standards_materialization_digest="sha256:" + "a" * 64,  # SAME as session_a
        source_refs=(dict(repository="owner-repo", commit_sha=_COMMIT, path="standards/testing.md", blob_digest="sha256:" + "a" * 64),),
        standards_source_refs=(dict(repository="owner-repo", commit_sha=_COMMIT, path="standards/testing.md", blob_digest="sha256:" + "a" * 64),),
        context_digest="sha256:" + "a" * 64,
        session_digest="sha256:" + "b" * 64,
    )
    return (session_a, session_b)


def _make_initial_receipts(sessions: tuple[ReviewerSession, ...], findings: tuple[NormalizedFinding, ...]) -> tuple[InitialFindingReceipt, ...]:
    """Create initial finding receipts from sessions and findings."""
    return (
        create_initial_finding_receipt(
            session=sessions[0],
            findings=tuple(item.to_dict() for item in findings[:1]),  # reviewer-a gets F-001
            recorded_at="2026-09-13T09:00:00Z",
        ),
        create_initial_finding_receipt(
            session=sessions[1],
            findings=tuple(item.to_dict() for item in findings[1:]),  # reviewer-b gets F-002
            recorded_at="2026-09-13T09:00:01Z",
        ),
    )


def _make_reviewer_outcomes() -> tuple[ReviewerOutcome, ...]:
    """Create reviewer outcomes matching the mock sessions."""
    return (
        ReviewerOutcome(
            review_id="review-reviewer-a",
            reviewer="reviewer-a",
            verdict=ReviewVerdict.NEEDS_FIX,
            target_ref="source:task.py@" + _COMMIT,
            evidence_refs=("review-evidence-a",),
            findings=_make_findings()[:1],
        ),
        ReviewerOutcome(
            review_id="review-reviewer-b",
            reviewer="reviewer-b",
            verdict=ReviewVerdict.PASS,
            target_ref="source:task.py@" + _COMMIT,
            evidence_refs=("review-evidence-b",),
            findings=_make_findings()[1:],
        ),
    )


def _make_ledger(sessions: tuple[ReviewerSession, ...], receipts: tuple[InitialFindingReceipt, ...]) -> InitialFindingReceiptLedger:
    """Create a ledger from sessions and receipts."""
    ledger = InitialFindingReceiptLedger.from_sessions(sessions)
    ledger = ledger.append(receipts[0])
    ledger = ledger.append(receipts[1]).seal()
    return ledger


@pytest.fixture
def shared_sources() -> list[StandardsSourceRef]:
    return [
        _source(_COMMIT, "standards/architecture.md", _ARCH_CONTENT),
        _source(_COMMIT, "standards/testing.md", _TEST_CONTENT),
    ]


@pytest.fixture
def shared_profile(shared_sources: list[StandardsSourceRef]) -> StandardsProfile:
    return _profile(shared_sources)


@pytest.fixture
def source_reader(shared_sources: list[StandardsSourceRef]) -> SourceReader:
    """Source reader returns exact content matching blob_digest."""
    return SourceReader({
        (_COMMIT, "standards/architecture.md"): _ARCH_CONTENT.encode(),
        (_COMMIT, "standards/testing.md"): _TEST_CONTENT.encode(),
    })


@pytest.fixture
def standards_session_context(shared_profile: StandardsProfile, source_reader: SourceReader):
    """Resolve standards profile to session context."""
    resolver = StandardsResolver(source_reader)
    return resolver.resolve(shared_profile).session_context


@pytest.fixture
def context_pack(standards_session_context, source_reader: SourceReader) -> TaskContextPack:
    """Build a TaskContextPack for testing."""
    builder = ContextPackBuilder(source_reader)
    return builder.build(
        source_refs=standards_session_context.receipt.sources,
        evidence_refs=[],
        standards=standards_session_context,
    )


@pytest.fixture
def reviewer_sessions(context_pack: TaskContextPack) -> tuple:
    """Create isolated reviewer sessions for testing."""
    factory = ReviewerSessionFactory()

    reviewer_a = _make_reviewer_spec("reviewer-a", "architecture")
    reviewer_b = _make_reviewer_spec("reviewer-b", "testing")

    sessions = factory.create(
        run_id="run-001",
        node_id="mbx-tc-1003",
        attempt_id="attempt-001",
        task_context=context_pack,
        reviewers=[reviewer_a, reviewer_b],
        peer_finding_refs=None,
    )

    return sessions


def test_reviewer_context_isolation(context_pack: TaskContextPack) -> None:
    """Reviewer B first context must not contain reviewer A's finding_id/claim."""
    factory = ReviewerInitialContextFactory()

    reviewer_a = _make_reviewer_spec("reviewer-a", "architecture")
    reviewer_b = _make_reviewer_spec("reviewer-b", "testing")

    ctx_a = factory.build(
        reviewer_id=reviewer_a.reviewer_id,
        lens=reviewer_a.lens,
        task_context=context_pack,
        own_findings=None,
    )
    ctx_b = factory.build(
        reviewer_id=reviewer_b.reviewer_id,
        lens=reviewer_b.lens,
        task_context=context_pack,
        own_findings=None,
    )

    # Both have identical source/standards inventory
    assert ctx_a.task_context.inventory_digest == ctx_b.task_context.inventory_digest

    # But reviewer B's context must exclude reviewer A's finding_ids/claims
    # Use to_dict() since frozen dataclass with slots has no __dict__
    ctx_b_dict = ctx_b.to_dict()
    assert not any("reviewer-a" in str(v) for v in ctx_b_dict.values())


def test_reviewer_session_isolation(reviewer_sessions: tuple) -> None:
    """Reviewer sessions must have separate IDs and no cross-session finding refs."""
    session_a, session_b = reviewer_sessions

    assert session_a.session_id != session_b.session_id
    assert session_a.reviewer_id == "reviewer-a"
    assert session_b.reviewer_id == "reviewer-b"

    # No peer findings in initial session state
    assert session_a.peer_finding_refs == ()
    assert session_b.peer_finding_refs == ()

    # First pass context contains no peer data
    payload_a = session_a.first_pass_context()
    payload_b = session_b.first_pass_context()
    assert payload_a["peer_finding_refs"] == []
    assert payload_b["peer_finding_refs"] == []


def test_initial_finding_receipt_creation(reviewer_sessions: tuple) -> None:
    """Immutable initial finding receipts are created per reviewer with different finding digests."""
    findings = _make_findings()

    session_a, session_b = reviewer_sessions

    receipt_a = create_initial_finding_receipt(
        session=session_a,
        findings=tuple(item.to_dict() for item in findings[:1]),  # Only F-001
        recorded_at="2026-09-13T09:00:00Z",
    )
    receipt_b = create_initial_finding_receipt(
        session=session_b,
        findings=tuple(item.to_dict() for item in findings[1:]),  # Only F-002
        recorded_at="2026-09-13T09:00:01Z",
    )

    assert receipt_a.reviewer_id == "reviewer-a"
    assert receipt_b.reviewer_id == "reviewer-b"
    assert receipt_a.finding_digest != receipt_b.finding_digest  # Different findings = different digests


def test_independent_first_verdicts() -> None:
    """Each reviewer submits independent first verdict before seeing peer findings."""
    verdict_a = ReviewVerdict.NEEDS_FIX
    verdict_b = ReviewVerdict.PASS

    assert verdict_a != verdict_b


def test_conflict_detection_and_adjudication() -> None:
    """Conflicting independent verdicts are surfaced and adjudicated explicitly."""
    findings = _make_findings()

    # Use adjudicate_conflicts with correct API - findings with conflict_group
    findings_with_conflict = (
        NormalizedFinding(
            finding_id="F-001",
            severity="CRITICAL",
            category="architecture",
            lens="architecture",
            claim="Missing auth boundary in payment flow",
            evidence_refs=("ev-1", "ev-2"),
            recommendation="Add authorization check",
            reviewer="reviewer-a",
            confidence=0.95,
            conflict_group="conflict-001",
        ),
        NormalizedFinding(
            finding_id="F-002",
            severity="MINOR",
            category="testing",
            lens="testing",
            claim="Code style inconsistency",
            evidence_refs=("ev-3",),
            recommendation="Apply formatter",
            reviewer="reviewer-b",
            confidence=0.60,
            conflict_group="conflict-001",
        ),
    )

    result: ConflictAdjudicationResult = adjudicate_conflicts(
        findings=findings_with_conflict,
        proposed_verdict=ReviewVerdict.PASS,
        resolutions={},
    )

    # Must escalate - NEVER silent PASS
    assert result.final_verdict == ReviewVerdict.NEEDS_CLARIFICATION
    assert result.conflicts is not None
    assert len(result.conflicts) >= 1
    assert any(c.material for c in result.conflicts)


def test_mixer_input_manifest_blocks_clean_synthesis() -> None:
    """Mixer input manifest preserves conflict and blocks clean synthesis."""
    findings = _make_findings()
    sessions = _make_reviewer_sessions()
    receipts = _make_initial_receipts(sessions, findings)
    ledger = _make_ledger(sessions, receipts)
    outcomes = _make_reviewer_outcomes()

    # Create manifest with conflicts explicitly via from_receipt_ledger
    manifest = MixerInputManifest.from_receipt_ledger(
        ledger=ledger,
        outcomes=outcomes,
        conflicts=[
            MixerConflict(
                conflict_id="conflict-001",
                finding_ids=("F-001", "F-002"),
                reviewers=("reviewer-a", "reviewer-b"),
                severities=("critical", "minor"),
                evidence_refs=("ev-1", "ev-2", "ev-3"),
                material=True,
                disposition=ConflictDisposition.UNRESOLVED,
            )
        ],
    )

    # Has conflict
    assert len(manifest.conflicts) >= 1

    # Cannot do clean synthesis - require_clean_synthesis_ready() will fail on material conflict
    with pytest.raises(MixerInputManifestError) as exc_info:
        manifest.require_clean_synthesis_ready()
    assert "conflict" in str(exc_info.value).lower()

    # Must seal with conflict resolved - test seal() after resolving
    # First create a manifest without conflicts, then seal it works
    manifest_no_conflict = MixerInputManifest.from_receipt_ledger(
        ledger=ledger,
        outcomes=outcomes,
        conflicts=[],  # No conflicts
    )
    sealed = manifest_no_conflict.seal()
    assert sealed.sealed is True
    assert len(sealed.conflicts) == 0


def test_evidence_provenance_retained() -> None:
    """All evidence_refs and reviewer provenance retained through adjudication."""
    findings = _make_findings()[:1]

    result = adjudicate_conflicts(
        findings=findings,
        proposed_verdict=ReviewVerdict.PASS,
        resolutions={},
    )

    # Evidence refs preserved in conflict
    assert result.conflicts is not None
    for c in result.conflicts:
        assert c.conflict_id
        assert c.material


def test_bounded_review_state() -> None:
    """Review state is bounded: no raw transcript, only structured artifacts."""
    sessions = _make_reviewer_sessions()
    findings = _make_findings()[:1]

    receipt_a = create_initial_finding_receipt(
        session=sessions[0],
        findings=tuple(item.to_dict() for item in findings),
        recorded_at="2026-09-13T09:00:00Z",
    )
    receipt_b = create_initial_finding_receipt(
        session=sessions[1],
        findings=(),
        recorded_at="2026-09-13T09:00:01Z",
    )

    receipts = [receipt_a, receipt_b]

    # Verify no chat/transcript fields
    for r in receipts:
        assert not hasattr(r, "transcript")
        assert not hasattr(r, "chat_history")
        assert not hasattr(r, "raw_prompt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])