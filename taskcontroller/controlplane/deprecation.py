"""Measured criteria for retiring the direct-message/task-payload fallback.

This module is a pure qualification boundary.  It accepts machine-readable
scenario measurements and returns an eligibility decision; it never removes a
fallback, dispatches work, or mutates durable state.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


DEPRECATION_CRITERIA_PROTOCOL = "dw.taskcontroller.deprecation-criteria/v1"
_IMPLEMENTATION_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EVIDENCE_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:(?:/{0,2})[^\s]+$")


class DeprecationEvidenceError(ValueError):
    """Fail-closed validation error for measured deprecation evidence."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class EvidenceScenario(str, Enum):
    """Required measured scenarios before legacy fallback retirement."""

    LIVE_RUN = "live_run"
    RECOVERY = "recovery"
    FANOUT = "fanout"
    CROSS_REVIEW = "cross_review"
    TAKEOVER = "takeover"


class DeprecationStatus(str, Enum):
    """Qualification result; this policy never performs retirement."""

    HOLD = "HOLD"
    ELIGIBLE = "ELIGIBLE"


_REQUIRED_SCENARIOS = tuple(EvidenceScenario)


def _require_positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        raise DeprecationEvidenceError(
            "COUNT_INVALID", f"{field} must be a positive integer"
        )
    return value


def _require_nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise DeprecationEvidenceError(
            "COUNT_INVALID", f"{field} must be a non-negative integer"
        )
    return value


def _require_head(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _IMPLEMENTATION_HEAD_PATTERN.fullmatch(value):
        raise DeprecationEvidenceError(
            "HEAD_INVALID", f"{field} must be a 40-character lowercase SHA"
        )
    return value


def _coerce_scenario(value: EvidenceScenario | str) -> EvidenceScenario:
    try:
        return EvidenceScenario(value)
    except (TypeError, ValueError) as exc:
        raise DeprecationEvidenceError(
            "SCENARIO_INVALID", f"unsupported evidence scenario {value!r}"
        ) from exc


def _validate_evidence_refs(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise DeprecationEvidenceError(
            "EVIDENCE_REF_INVALID", "evidence_refs must be a sequence"
        )
    if not values:
        raise DeprecationEvidenceError(
            "EVIDENCE_REF_INVALID", "at least one machine evidence reference is required"
        )

    refs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not _EVIDENCE_REF_PATTERN.fullmatch(value):
            raise DeprecationEvidenceError(
                "EVIDENCE_REF_INVALID",
                "references must be scheme-qualified machine evidence refs",
            )
        refs.append(value)
    if len(set(refs)) != len(refs):
        raise DeprecationEvidenceError(
            "EVIDENCE_REF_INVALID", "evidence_refs must not contain duplicates"
        )
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True)
class DeprecationCriteria:
    """Explicit sample and success thresholds for every required scenario."""

    minimum_measured_live_runs: int = 1
    minimum_successful_live_runs: int = 1
    minimum_measured_recovery_runs: int = 1
    minimum_successful_recovery_runs: int = 1
    minimum_measured_fanout_runs: int = 1
    minimum_successful_fanout_runs: int = 1
    minimum_measured_cross_review_runs: int = 1
    minimum_successful_cross_review_runs: int = 1
    minimum_measured_takeover_runs: int = 1
    minimum_successful_takeover_runs: int = 1

    def __post_init__(self) -> None:
        for field_name in (
            "minimum_measured_live_runs",
            "minimum_successful_live_runs",
            "minimum_measured_recovery_runs",
            "minimum_successful_recovery_runs",
            "minimum_measured_fanout_runs",
            "minimum_successful_fanout_runs",
            "minimum_measured_cross_review_runs",
            "minimum_successful_cross_review_runs",
            "minimum_measured_takeover_runs",
            "minimum_successful_takeover_runs",
        ):
            _require_positive_int(getattr(self, field_name), field_name)

    def minimums(self, scenario: EvidenceScenario) -> tuple[int, int]:
        values = {
            EvidenceScenario.LIVE_RUN: (
                self.minimum_measured_live_runs,
                self.minimum_successful_live_runs,
            ),
            EvidenceScenario.RECOVERY: (
                self.minimum_measured_recovery_runs,
                self.minimum_successful_recovery_runs,
            ),
            EvidenceScenario.FANOUT: (
                self.minimum_measured_fanout_runs,
                self.minimum_successful_fanout_runs,
            ),
            EvidenceScenario.CROSS_REVIEW: (
                self.minimum_measured_cross_review_runs,
                self.minimum_successful_cross_review_runs,
            ),
            EvidenceScenario.TAKEOVER: (
                self.minimum_measured_takeover_runs,
                self.minimum_successful_takeover_runs,
            ),
        }
        return values[scenario]

    def to_dict(self) -> dict[str, int]:
        return {
            "minimum_measured_live_runs": self.minimum_measured_live_runs,
            "minimum_successful_live_runs": self.minimum_successful_live_runs,
            "minimum_measured_recovery_runs": self.minimum_measured_recovery_runs,
            "minimum_successful_recovery_runs": self.minimum_successful_recovery_runs,
            "minimum_measured_fanout_runs": self.minimum_measured_fanout_runs,
            "minimum_successful_fanout_runs": self.minimum_successful_fanout_runs,
            "minimum_measured_cross_review_runs": self.minimum_measured_cross_review_runs,
            "minimum_successful_cross_review_runs": self.minimum_successful_cross_review_runs,
            "minimum_measured_takeover_runs": self.minimum_measured_takeover_runs,
            "minimum_successful_takeover_runs": self.minimum_successful_takeover_runs,
        }


@dataclass(frozen=True, slots=True)
class ScenarioEvidence:
    """Measured evidence for one exact implementation-head scenario."""

    scenario: EvidenceScenario
    measured_samples: int
    successful_samples: int
    exact_impl_head: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario", _coerce_scenario(self.scenario))
        measured = _require_positive_int(self.measured_samples, "measured_samples")
        successful = _require_nonnegative_int(
            self.successful_samples, "successful_samples"
        )
        if successful > measured:
            raise DeprecationEvidenceError(
                "COUNT_INVALID", "successful_samples cannot exceed measured_samples"
            )
        object.__setattr__(self, "measured_samples", measured)
        object.__setattr__(self, "successful_samples", successful)
        object.__setattr__(
            self, "exact_impl_head", _require_head(self.exact_impl_head, "exact_impl_head")
        )
        object.__setattr__(self, "evidence_refs", _validate_evidence_refs(self.evidence_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "measured_samples": self.measured_samples,
            "successful_samples": self.successful_samples,
            "exact_impl_head": self.exact_impl_head,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class DeprecationDecision:
    """Immutable qualification result with no retirement side effect."""

    status: DeprecationStatus
    fallback_removal_allowed: bool
    failed_criteria: tuple[str, ...]
    scenario_evidence: tuple[ScenarioEvidence, ...]
    expected_impl_head: str
    criteria: DeprecationCriteria
    unresolved_severity_loss_defects: int
    protocol: str = DEPRECATION_CRITERIA_PROTOCOL

    def __post_init__(self) -> None:
        try:
            status = DeprecationStatus(self.status)
        except (TypeError, ValueError) as exc:
            raise DeprecationEvidenceError(
                "STATUS_INVALID", "status must be HOLD or ELIGIBLE"
            ) from exc
        object.__setattr__(self, "status", status)
        if type(self.fallback_removal_allowed) is not bool:
            raise DeprecationEvidenceError(
                "DECISION_INVALID", "fallback_removal_allowed must be boolean"
            )
        if not isinstance(self.criteria, DeprecationCriteria):
            raise DeprecationEvidenceError("CRITERIA_INVALID", "criteria is invalid")
        object.__setattr__(
            self,
            "expected_impl_head",
            _require_head(self.expected_impl_head, "expected_impl_head"),
        )
        defects = _require_nonnegative_int(
            self.unresolved_severity_loss_defects,
            "unresolved_severity_loss_defects",
        )
        object.__setattr__(self, "unresolved_severity_loss_defects", defects)
        failures = tuple(sorted(set(self.failed_criteria)))
        object.__setattr__(self, "failed_criteria", failures)
        evidence = tuple(self.scenario_evidence)
        if any(not isinstance(item, ScenarioEvidence) for item in evidence):
            raise DeprecationEvidenceError(
                "EVIDENCE_INVALID", "scenario_evidence contains an invalid item"
            )
        object.__setattr__(self, "scenario_evidence", evidence)
        if (status is DeprecationStatus.ELIGIBLE) != self.fallback_removal_allowed:
            raise DeprecationEvidenceError(
                "DECISION_INVALID", "eligibility and removal permission must agree"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "status": self.status.value,
            "action": "QUALIFY_ONLY",
            "fallback_removal_allowed": self.fallback_removal_allowed,
            "fallbacks_removed": False,
            "expected_impl_head": self.expected_impl_head,
            "unresolved_severity_loss_defects": self.unresolved_severity_loss_defects,
            "failed_criteria": list(self.failed_criteria),
            "criteria": self.criteria.to_dict(),
            "scenario_measurements": [
                item.to_dict()
                for item in sorted(
                    self.scenario_evidence,
                    key=lambda item: item.scenario.value,
                )
            ],
        }


def evaluate_deprecation(
    *,
    evidence: Iterable[ScenarioEvidence],
    expected_impl_head: str,
    criteria: DeprecationCriteria | None = None,
    unresolved_severity_loss_defects: int = 0,
) -> DeprecationDecision:
    """Return eligibility only after every measured criterion is satisfied."""

    expected_head = _require_head(expected_impl_head, "expected_impl_head")
    active_criteria = criteria if criteria is not None else DeprecationCriteria()
    if not isinstance(active_criteria, DeprecationCriteria):
        raise DeprecationEvidenceError("CRITERIA_INVALID", "criteria is invalid")
    defects = _require_nonnegative_int(
        unresolved_severity_loss_defects,
        "unresolved_severity_loss_defects",
    )
    if isinstance(evidence, (str, bytes, bytearray)):
        raise DeprecationEvidenceError("EVIDENCE_INVALID", "evidence must be iterable")

    try:
        evidence_items = tuple(evidence)
    except TypeError as exc:
        raise DeprecationEvidenceError("EVIDENCE_INVALID", "evidence must be iterable") from exc
    if any(not isinstance(item, ScenarioEvidence) for item in evidence_items):
        raise DeprecationEvidenceError(
            "EVIDENCE_INVALID", "evidence contains a non-ScenarioEvidence item"
        )

    by_scenario: dict[EvidenceScenario, ScenarioEvidence] = {}
    for item in evidence_items:
        if item.scenario in by_scenario:
            raise DeprecationEvidenceError(
                "DUPLICATE_SCENARIO", f"duplicate evidence for {item.scenario.value}"
            )
        by_scenario[item.scenario] = item

    failures: list[str] = []
    for scenario in _REQUIRED_SCENARIOS:
        item = by_scenario.get(scenario)
        if item is None:
            failures.append(f"missing:{scenario.value}")
            continue
        minimum_measured, minimum_successful = active_criteria.minimums(scenario)
        if item.measured_samples < minimum_measured:
            failures.append(
                f"{scenario.value}:measured_samples<{minimum_measured}"
            )
        if item.successful_samples < minimum_successful:
            failures.append(
                f"{scenario.value}:successful_samples<{minimum_successful}"
            )
        if item.exact_impl_head != expected_head:
            failures.append(f"{scenario.value}:exact_impl_head_mismatch")

    if defects > 0:
        failures.append("unresolved_severity_loss_defects>0")

    ordered_failures = tuple(sorted(set(failures)))
    status = DeprecationStatus.HOLD if ordered_failures else DeprecationStatus.ELIGIBLE
    return DeprecationDecision(
        status=status,
        fallback_removal_allowed=status is DeprecationStatus.ELIGIBLE,
        failed_criteria=ordered_failures,
        scenario_evidence=tuple(
            by_scenario[scenario]
            for scenario in _REQUIRED_SCENARIOS
            if scenario in by_scenario
        ),
        expected_impl_head=expected_head,
        criteria=active_criteria,
        unresolved_severity_loss_defects=defects,
    )


__all__ = [
    "DEPRECATION_CRITERIA_PROTOCOL",
    "DeprecationCriteria",
    "DeprecationDecision",
    "DeprecationEvidenceError",
    "DeprecationStatus",
    "EvidenceScenario",
    "ScenarioEvidence",
    "evaluate_deprecation",
]
