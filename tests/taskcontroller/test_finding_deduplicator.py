"""TC-MBX-603: semantic finding deduplication with full provenance."""

from __future__ import annotations

import pytest

from taskcontroller.execution.result_normalizer import NormalizedFinding
from taskcontroller.execution.finding_deduplicator import (
    FindingDeduplicationError,
    deduplicate_findings,
)


def _finding(
    *,
    finding_id: str,
    reviewer: str,
    claim: str = "Unsafe boundary is reachable",
    severity: str = "major",
    category: str = "security",
    lens: str = "security-reliability",
    evidence_refs: tuple[str, ...] = ("artifact-a",),
    recommendation: str = "Block release",
    conflict_group: str | None = None,
    confidence: float | None = 0.8,
) -> NormalizedFinding:
    return NormalizedFinding(
        finding_id=finding_id,
        severity=severity,
        category=category,
        lens=lens,
        claim=claim,
        evidence_refs=evidence_refs,
        recommendation=recommendation,
        reviewer=reviewer,
        conflict_group=conflict_group,
        confidence=confidence,
    )


def test_semantic_duplicates_collapse_and_retain_every_provenance_ref() -> None:
    first = _finding(
        finding_id="finding-a",
        reviewer="reviewer-a",
        evidence_refs=("artifact-a", "line-10"),
        conflict_group="conflict-a",
    )
    second = _finding(
        finding_id="finding-b",
        reviewer="reviewer-b",
        claim=" unsafe   boundary is reachable ",
        recommendation=" block   release ",
        evidence_refs=("artifact-b",),
        conflict_group="conflict-b",
    )

    result = deduplicate_findings((first, second))

    assert result.source_count == 2
    assert result.deduplicated_count == 1
    deduplicated = result.findings[0]
    assert deduplicated.provenance_count == 2
    assert [item.source_finding_id for item in deduplicated.provenance] == [
        "finding-a",
        "finding-b",
    ]
    assert [item.reviewer for item in deduplicated.provenance] == [
        "reviewer-a",
        "reviewer-b",
    ]
    assert deduplicated.provenance[0].evidence_refs == ("artifact-a", "line-10")
    assert deduplicated.provenance[1].evidence_refs == ("artifact-b",)
    assert [item.conflict_group for item in deduplicated.provenance] == [
        "conflict-a",
        "conflict-b",
    ]


def test_severity_disagreement_is_not_semantically_deduplicated() -> None:
    major = _finding(finding_id="finding-major", reviewer="reviewer-a", severity="major")
    critical = _finding(
        finding_id="finding-critical",
        reviewer="reviewer-b",
        severity="critical",
    )

    result = deduplicate_findings((major, critical))

    assert result.deduplicated_count == 2
    assert [item.representative.severity for item in result.findings] == [
        "critical",
        "major",
    ]


def test_non_semantic_fields_do_not_change_deterministic_grouping_or_order() -> None:
    first = _finding(finding_id="z-source", reviewer="reviewer-z", category="reliability")
    second = _finding(finding_id="a-source", reviewer="reviewer-a", category="security")

    left = deduplicate_findings((first, second))
    right = deduplicate_findings((second, first))

    assert left.to_dict() == right.to_dict()
    assert [item.representative.category for item in left.findings] == [
        "reliability",
        "security",
    ]


def test_different_lens_or_claim_remains_a_distinct_finding() -> None:
    base = _finding(finding_id="finding-a", reviewer="reviewer-a")
    other_lens = _finding(
        finding_id="finding-b",
        reviewer="reviewer-b",
        lens="implementation",
    )
    other_claim = _finding(
        finding_id="finding-c",
        reviewer="reviewer-c",
        claim="Different unsafe boundary is reachable",
    )

    result = deduplicate_findings((base, other_lens, other_claim))

    assert result.deduplicated_count == 3


def test_duplicate_delivery_is_preserved_as_a_source_reference() -> None:
    finding = _finding(finding_id="finding-a", reviewer="reviewer-a")

    result = deduplicate_findings((finding, finding))

    assert result.source_count == 2
    assert result.findings[0].provenance_count == 2
    assert [item.source_finding_id for item in result.findings[0].provenance] == [
        "finding-a",
        "finding-a",
    ]


def test_result_is_immutable_and_does_not_mutate_normalized_input() -> None:
    source = _finding(finding_id="finding-a", reviewer="reviewer-a")
    before = source.to_dict()

    result = deduplicate_findings((source,))

    assert source.to_dict() == before
    with pytest.raises(Exception):
        result.findings = ()  # type: ignore[misc]
    with pytest.raises(Exception):
        result.findings[0].provenance = ()  # type: ignore[misc]


def test_invalid_input_fails_closed() -> None:
    with pytest.raises(FindingDeduplicationError, match="NormalizedFinding"):
        deduplicate_findings(({"finding_id": "not-a-finding"},))  # type: ignore[arg-type]
