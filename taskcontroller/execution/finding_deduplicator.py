"""Provider-neutral semantic deduplication for normalized review findings.

This module is a pure pre-Mixer seam.  It groups semantically equivalent
``NormalizedFinding`` values without invoking reviewers/providers or mutating
runtime state.  Every input finding remains recoverable through provenance.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from taskcontroller.execution.result_normalizer import NormalizedFinding
from taskcontroller.execution.errors import ExecutionFabricError


FINDING_DEDUPLICATOR_PROTOCOL = "dw.taskcontroller.finding-deduplicator/v1"


class FindingDeduplicationError(ExecutionFabricError):
    """Raised when a deduplication input or result boundary is invalid."""


def _semantic_text(value: str) -> str:
    """Canonicalize human text for semantic comparison, not evidence output."""

    return " ".join(value.split()).casefold()


def _semantic_key(finding: NormalizedFinding) -> tuple[Any, ...]:
    """Return identity fields while excluding source-specific provenance fields."""

    return (
        finding.severity,
        _semantic_text(finding.category),
        _semantic_text(finding.lens),
        _semantic_text(finding.claim),
        _semantic_text(finding.recommendation),
        finding.disposition,
        finding.confidence,
    )


def _source_sort_key(finding: NormalizedFinding) -> tuple[Any, ...]:
    """Choose a deterministic representative and provenance order."""

    return (
        finding.finding_id,
        finding.reviewer,
        finding.evidence_refs,
        finding.conflict_group or "",
        json.dumps(finding.to_dict(), sort_keys=True, separators=(",", ":")),
    )


@dataclass(frozen=True, slots=True)
class FindingProvenance:
    """One recoverable source reference retained after semantic collapse."""

    source_finding_id: str
    reviewer: str
    evidence_refs: tuple[str, ...]
    conflict_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_finding_id, str) or not self.source_finding_id:
            raise FindingDeduplicationError("source_finding_id must be non-empty")
        if not isinstance(self.reviewer, str) or not self.reviewer:
            raise FindingDeduplicationError("reviewer must be non-empty")
        refs = tuple(self.evidence_refs)
        if not refs or any(not isinstance(ref, str) or not ref for ref in refs):
            raise FindingDeduplicationError("evidence_refs must contain non-empty strings")
        object.__setattr__(self, "evidence_refs", refs)
        if self.conflict_group is not None and (
            not isinstance(self.conflict_group, str) or not self.conflict_group
        ):
            raise FindingDeduplicationError("conflict_group must be non-empty when present")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_finding_id": self.source_finding_id,
            "reviewer": self.reviewer,
            "evidence_refs": list(self.evidence_refs),
        }
        if self.conflict_group is not None:
            result["conflict_group"] = self.conflict_group
        return result


@dataclass(frozen=True, slots=True)
class DeduplicatedFinding:
    """Representative finding plus all source provenance for its semantic group."""

    representative: NormalizedFinding
    provenance: tuple[FindingProvenance, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.representative, NormalizedFinding):
            raise FindingDeduplicationError("representative must be a NormalizedFinding")
        provenance = tuple(self.provenance)
        if not provenance or any(not isinstance(item, FindingProvenance) for item in provenance):
            raise FindingDeduplicationError(
                "provenance must contain at least one FindingProvenance"
            )
        object.__setattr__(self, "provenance", provenance)

    @property
    def provenance_count(self) -> int:
        return len(self.provenance)

    def to_dict(self) -> dict[str, Any]:
        result = self.representative.to_dict()
        result["provenance"] = [item.to_dict() for item in self.provenance]
        result["provenance_count"] = self.provenance_count
        return result


@dataclass(frozen=True, slots=True)
class FindingDeduplicationResult:
    """Deterministic immutable output of one bounded deduplication pass."""

    findings: tuple[DeduplicatedFinding, ...]
    source_count: int

    def __post_init__(self) -> None:
        findings = tuple(self.findings)
        if any(not isinstance(item, DeduplicatedFinding) for item in findings):
            raise FindingDeduplicationError(
                "findings must contain DeduplicatedFinding values"
            )
        if not isinstance(self.source_count, int) or isinstance(self.source_count, bool):
            raise FindingDeduplicationError("source_count must be an integer")
        if self.source_count < len(findings):
            raise FindingDeduplicationError(
                "source_count cannot be less than deduplicated finding count"
            )
        object.__setattr__(self, "findings", findings)

    @property
    def deduplicated_count(self) -> int:
        return len(self.findings)

    @property
    def provenance_count(self) -> int:
        return sum(item.provenance_count for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": FINDING_DEDUPLICATOR_PROTOCOL,
            "source_count": self.source_count,
            "deduplicated_count": self.deduplicated_count,
            "provenance_count": self.provenance_count,
            "findings": [item.to_dict() for item in self.findings],
        }


def deduplicate_findings(
    findings: Iterable[NormalizedFinding],
) -> FindingDeduplicationResult:
    """Collapse semantic duplicates while retaining every source reference."""

    try:
        source_findings = tuple(findings)
    except TypeError as exc:
        raise FindingDeduplicationError("findings must be iterable") from exc
    if any(not isinstance(item, NormalizedFinding) for item in source_findings):
        raise FindingDeduplicationError("findings must contain NormalizedFinding values")

    groups: dict[tuple[Any, ...], list[NormalizedFinding]] = defaultdict(list)
    for finding in source_findings:
        groups[_semantic_key(finding)].append(finding)

    deduplicated: list[DeduplicatedFinding] = []
    for key in sorted(groups):
        sources = sorted(groups[key], key=_source_sort_key)
        representative = sources[0]
        provenance = tuple(
            FindingProvenance(
                source_finding_id=item.finding_id,
                reviewer=item.reviewer,
                evidence_refs=tuple(item.evidence_refs),
                conflict_group=item.conflict_group,
            )
            for item in sources
        )
        deduplicated.append(
            DeduplicatedFinding(
                representative=representative,
                provenance=provenance,
            )
        )

    return FindingDeduplicationResult(
        findings=tuple(deduplicated),
        source_count=len(source_findings),
    )
