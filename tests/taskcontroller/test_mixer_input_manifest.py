"""TC-MBX-603: immutable Mixer input manifest and evidence policy."""

from __future__ import annotations

import hashlib
import json

import pytest

from taskcontroller.domain.enums import ReviewVerdict
from taskcontroller.execution.initial_finding_receipt import (
    InitialFindingReceiptLedger,
    create_initial_finding_receipt,
)
from taskcontroller.execution.mixer_input_manifest import (
    ConflictPolicy,
    MixerConflict,
    MixerInputManifest,
    MixerInputManifestError,
    QuorumPolicy,
)
from taskcontroller.execution.result_normalizer import NormalizedFinding
from taskcontroller.execution.severity_preservation import ReviewerOutcome
from taskcontroller.standards import StandardsProfile, StandardsResolver, StandardsSourceRef
from taskcontroller.standards.context_pack import ContextPackBuilder
from taskcontroller.standards.reviewer_session import ReviewerSessionFactory, ReviewerSpec


_COMMIT = "e" * 40


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
        run_id="run-603",
        node_id="node-603",
        attempt_id="attempt-603",
        task_context=_task_context_pack(),
        reviewers=(
            ReviewerSpec(reviewer_id="reviewer-a", lens="architecture"),
            ReviewerSpec(reviewer_id="reviewer-b", lens="security"),
        ),
    )


def _finding(
    finding_id: str,
    reviewer: str,
    *,
    severity: str = "minor",
    claim: str | None = None,
    evidence_refs: tuple[str, ...] | None = None,
    conflict_group: str | None = None,
) -> NormalizedFinding:
    return NormalizedFinding(
        finding_id=finding_id,
        severity=severity,
        category="boundary",
        lens="architecture",
        claim=claim or f"claim-{finding_id}",
        evidence_refs=evidence_refs or (f"evidence-{finding_id}",),
        recommendation=f"recommendation-{finding_id}",
        reviewer=reviewer,
        conflict_group=conflict_group,
    )


def _outcome(reviewer: str, findings: tuple[NormalizedFinding, ...], *, verdict=ReviewVerdict.PASS):
    return ReviewerOutcome(
        review_id=f"review-{reviewer}",
        reviewer=reviewer,
        verdict=verdict,
        target_ref="source:task.py@" + _COMMIT,
        evidence_refs=(f"review-evidence-{reviewer}",),
        findings=findings,
    )


def _ledger_and_outcomes(*, findings_a=None, findings_b=None, sealed=True):
    sessions = _sessions()
    findings_a = findings_a or (_finding("finding-a", "reviewer-a"),)
    findings_b = findings_b or (_finding("finding-b", "reviewer-b"),)
    outcomes = (
        _outcome("reviewer-a", findings_a),
        _outcome("reviewer-b", findings_b),
    )
    receipts = (
        create_initial_finding_receipt(
            session=sessions[0], findings=tuple(item.to_dict() for item in findings_a),
            recorded_at="2026-09-12T17:00:00Z",
        ),
        create_initial_finding_receipt(
            session=sessions[1], findings=tuple(item.to_dict() for item in findings_b),
            recorded_at="2026-09-12T17:01:00Z",
        ),
    )
    ledger = InitialFindingReceiptLedger.from_sessions(sessions)
    ledger = ledger.append(receipts[0])
    if sealed:
        ledger = ledger.append(receipts[1]).seal()
    return ledger, outcomes, receipts


def test_manifest_binds_receipts_quorum_findings_and_raw_output_digests() -> None:
    ledger, outcomes, receipts = _ledger_and_outcomes()

    manifest = MixerInputManifest.from_receipt_ledger(
        ledger,
        outcomes,
        raw_output_digests={
            "reviewer-a": "sha256:" + "1" * 64,
            "reviewer-b": "sha256:" + "2" * 64,
        },
    )

    assert manifest.quorum_policy is QuorumPolicy.ALL_REQUIRED
    assert manifest.conflict_policy is ConflictPolicy.PRESERVE_ALL
    assert manifest.ready_for_mixer is True
    assert manifest.missing_reviewer_ids == ()
    receipt_digests = tuple(
        sorted(item.receipt_digest for item in receipts if item.receipt_digest is not None)
    )
    assert manifest.received_receipt_digests == receipt_digests
    assert manifest.finding_ids == ("finding-a", "finding-b")
    assert manifest.raw_output_digests == (
        "sha256:" + "1" * 64,
        "sha256:" + "2" * 64,
    )
    payload = manifest.to_dict()
    assert payload["quorum"]["policy"] == "ALL_REQUIRED"
    assert payload["quorum"]["required_reviewer_ids"] == ["reviewer-a", "reviewer-b"]
    assert payload["manifest_digest"].startswith("sha256:")


def test_incomplete_quorum_is_retained_but_cannot_start_or_seal_mixer() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes(sealed=False)
    partial = InitialFindingReceiptLedger(
        required_sessions=ledger.required_sessions,
        receipts=(ledger.receipts[0],),
    )

    manifest = MixerInputManifest.from_receipt_ledger(
        partial,
        (outcomes[0],),
    )

    assert manifest.ready_for_mixer is False
    assert manifest.missing_reviewer_ids == ("reviewer-b",)
    with pytest.raises(MixerInputManifestError) as caught:
        manifest.require_mixer_ready()
    assert caught.value.code == "MIXER_QUORUM_INCOMPLETE"
    with pytest.raises(MixerInputManifestError) as caught:
        manifest.seal()
    assert caught.value.code == "MIXER_QUORUM_INCOMPLETE"


def test_material_disagreement_stays_visible_and_blocks_clean_synthesis() -> None:
    finding_a = _finding(
        "finding-a",
        "reviewer-a",
        severity="critical",
        claim="Boundary permits unsafe mutation",
        evidence_refs=("artifact-a", "line-10"),
        conflict_group="boundary-1",
    )
    finding_b = _finding(
        "finding-b",
        "reviewer-b",
        severity="major",
        claim="Boundary prevents unsafe mutation",
        evidence_refs=("artifact-b", "line-20"),
        conflict_group="boundary-1",
    )
    ledger, outcomes, _ = _ledger_and_outcomes(
        findings_a=(finding_a,), findings_b=(finding_b,)
    )
    conflict = MixerConflict(
        conflict_id="boundary-1",
        finding_ids=("finding-a", "finding-b"),
        reviewers=("reviewer-a", "reviewer-b"),
        severities=("critical", "major"),
        evidence_refs=("artifact-a", "artifact-b", "line-10", "line-20"),
        material=True,
    )

    manifest = MixerInputManifest.from_receipt_ledger(
        ledger,
        outcomes,
        conflicts=(conflict,),
    )

    assert manifest.material_conflict_ids == ("boundary-1",)
    assert manifest.unresolved_material_conflict_ids == ("boundary-1",)
    assert manifest.high_severity_finding_ids == ("finding-a", "finding-b")
    assert set(manifest.high_severity_evidence_refs) == {
        "artifact-a", "artifact-b", "line-10", "line-20"
    }
    assert manifest.to_dict()["conflicts"][0]["finding_ids"] == ["finding-a", "finding-b"]
    with pytest.raises(MixerInputManifestError) as caught:
        manifest.require_clean_synthesis_ready()
    assert caught.value.code == "MATERIAL_CONFLICT_UNRESOLVED"


def test_critical_and_major_inventory_cannot_be_dropped_from_manifest() -> None:
    critical = _finding("critical-1", "reviewer-a", severity="critical")
    major = _finding("major-1", "reviewer-b", severity="major")
    ledger, outcomes, _ = _ledger_and_outcomes(
        findings_a=(critical,), findings_b=(major,)
    )
    manifest = MixerInputManifest.from_receipt_ledger(ledger, outcomes)

    assert manifest.severity_inventory == {"critical": 1, "major": 1}
    assert manifest.high_severity_finding_ids == ("critical-1", "major-1")
    refs = set(manifest.high_severity_evidence_refs)
    assert refs == {"evidence-critical-1", "evidence-major-1"}
    encoded = json.dumps(manifest.to_dict(), sort_keys=True)
    assert "critical-1" in encoded and "major-1" in encoded
    assert "evidence-critical-1" in encoded and "evidence-major-1" in encoded


def test_raw_evidence_is_reference_only_and_never_serializes_transcript_content() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes()
    raw_digest = "sha256:" + "a" * 64
    manifest = MixerInputManifest.from_receipt_ledger(
        ledger,
        outcomes,
        raw_output_digests={"reviewer-a": raw_digest},
    )

    payload = manifest.to_dict()
    encoded = json.dumps(payload, sort_keys=True)
    assert raw_digest in encoded
    assert "transcript" not in encoded
    assert "raw_output" in encoded
    assert all(item.digest or item.kind.value != "RAW_OUTPUT" for item in manifest.raw_evidence_refs)


def test_mismatched_finding_digest_and_foreign_outcome_fail_closed() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes()
    changed = _finding("changed", "reviewer-a", severity="critical")
    bad_outcome = _outcome("reviewer-a", (changed,))
    with pytest.raises(MixerInputManifestError) as caught:
        MixerInputManifest.from_receipt_ledger(ledger, (bad_outcome, outcomes[1]))
    assert caught.value.code == "MIXER_FINDING_DIGEST_MISMATCH"

    foreign = _outcome("reviewer-x", (_finding("foreign", "reviewer-x"),))
    with pytest.raises(MixerInputManifestError) as caught:
        MixerInputManifest.from_receipt_ledger(ledger, (outcomes[0], outcomes[1], foreign))
    assert caught.value.code == "MIXER_REVIEWER_UNKNOWN"


def test_manifest_digest_is_order_independent_and_round_trips_immutably() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes()
    left = MixerInputManifest.from_receipt_ledger(ledger, outcomes)
    right = MixerInputManifest.from_receipt_ledger(ledger, tuple(reversed(outcomes)))

    assert left.to_dict() == right.to_dict()
    restored = MixerInputManifest.from_dict(left.to_dict())
    assert restored.to_dict() == left.to_dict()
    mutated = left.to_dict()
    mutated["reviewer_inputs"].clear()
    assert left.reviewer_ids == ("reviewer-a", "reviewer-b")


def test_duplicate_reviewer_or_finding_identity_is_rejected() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes()
    with pytest.raises(MixerInputManifestError) as caught:
        MixerInputManifest.from_receipt_ledger(ledger, (outcomes[0], outcomes[0], outcomes[1]))
    assert caught.value.code == "MIXER_REVIEWER_DUPLICATE"

    duplicate_ledger, duplicate_outcomes, _ = _ledger_and_outcomes(
        findings_b=(_finding("finding-a", "reviewer-b"),)
    )
    with pytest.raises(MixerInputManifestError) as caught:
        MixerInputManifest.from_receipt_ledger(
            duplicate_ledger, duplicate_outcomes
        )
    assert caught.value.code == "MIXER_FINDING_ID_CONFLICT"
