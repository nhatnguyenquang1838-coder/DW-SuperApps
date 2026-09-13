"""TC-MBX-906: measured deprecation criteria before legacy fallback removal."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from taskcontroller.controlplane.deprecation import (
    DEPRECATION_CRITERIA_PROTOCOL,
    DeprecationCriteria,
    DeprecationEvidenceError,
    DeprecationStatus,
    EvidenceScenario,
    ScenarioEvidence,
    evaluate_deprecation,
)


_HEAD = "24bc30ad43c722a066e1f37cdcb01af735c327b1"


def _scenario(
    scenario: EvidenceScenario,
    *,
    measured: int = 2,
    successful: int = 2,
    head: str = _HEAD,
    refs: tuple[str, ...] | None = None,
) -> ScenarioEvidence:
    return ScenarioEvidence(
        scenario=scenario,
        measured_samples=measured,
        successful_samples=successful,
        exact_impl_head=head,
        evidence_refs=refs or (f"run:tc-mbx-906/{scenario.value}",),
    )


def _all_scenarios(*, head: str = _HEAD) -> tuple[ScenarioEvidence, ...]:
    return tuple(_scenario(scenario, head=head) for scenario in EvidenceScenario)


def _criteria() -> DeprecationCriteria:
    return DeprecationCriteria(
        minimum_measured_live_runs=2,
        minimum_successful_live_runs=2,
        minimum_measured_recovery_runs=2,
        minimum_successful_recovery_runs=2,
        minimum_measured_fanout_runs=2,
        minimum_successful_fanout_runs=2,
        minimum_measured_cross_review_runs=2,
        minimum_successful_cross_review_runs=2,
        minimum_measured_takeover_runs=2,
        minimum_successful_takeover_runs=2,
    )


def test_complete_measured_evidence_qualifies_without_removing_fallback() -> None:
    decision = evaluate_deprecation(
        evidence=_all_scenarios(),
        expected_impl_head=_HEAD,
        criteria=_criteria(),
        unresolved_severity_loss_defects=0,
    )

    assert decision.status is DeprecationStatus.ELIGIBLE
    assert decision.fallback_removal_allowed is True
    assert decision.failed_criteria == ()
    assert decision.protocol == DEPRECATION_CRITERIA_PROTOCOL
    assert decision.to_dict()["action"] == "QUALIFY_ONLY"
    assert decision.to_dict()["fallbacks_removed"] is False


def test_missing_evidence_holds_for_each_required_scenario() -> None:
    decision = evaluate_deprecation(
        evidence=(),
        expected_impl_head=_HEAD,
        criteria=_criteria(),
    )

    assert decision.status is DeprecationStatus.HOLD
    assert decision.fallback_removal_allowed is False
    assert {
        f"missing:{scenario.value}" for scenario in EvidenceScenario
    }.issubset(set(decision.failed_criteria))


def test_under_measured_or_unsuccessful_scenario_holds() -> None:
    evidence = list(_all_scenarios())
    evidence[0] = _scenario(
        EvidenceScenario.LIVE_RUN,
        measured=1,
        successful=1,
    )
    evidence[1] = _scenario(
        EvidenceScenario.RECOVERY,
        measured=2,
        successful=1,
    )

    decision = evaluate_deprecation(
        evidence=evidence,
        expected_impl_head=_HEAD,
        criteria=_criteria(),
    )

    assert decision.status is DeprecationStatus.HOLD
    assert decision.fallback_removal_allowed is False
    assert "live_run:measured_samples<2" in decision.failed_criteria
    assert "live_run:successful_samples<2" in decision.failed_criteria
    assert "recovery:successful_samples<2" in decision.failed_criteria


def test_any_unresolved_severity_loss_defect_forces_hold() -> None:
    decision = evaluate_deprecation(
        evidence=_all_scenarios(),
        expected_impl_head=_HEAD,
        criteria=_criteria(),
        unresolved_severity_loss_defects=1,
    )

    assert decision.status is DeprecationStatus.HOLD
    assert decision.fallback_removal_allowed is False
    assert "unresolved_severity_loss_defects>0" in decision.failed_criteria


def test_evidence_must_bind_one_exact_implementation_head() -> None:
    evidence = list(_all_scenarios())
    evidence[-1] = _scenario(EvidenceScenario.TAKEOVER, head="f" * 40)

    decision = evaluate_deprecation(
        evidence=evidence,
        expected_impl_head=_HEAD,
        criteria=_criteria(),
    )

    assert decision.status is DeprecationStatus.HOLD
    assert "takeover:exact_impl_head_mismatch" in decision.failed_criteria


def test_date_only_or_readme_only_claim_is_not_evidence() -> None:
    with pytest.raises(DeprecationEvidenceError, match="EVIDENCE_REF_INVALID"):
        _scenario(
            EvidenceScenario.LIVE_RUN,
            refs=("2026-09-12", "README.md"),
        )


def test_duplicate_scenario_is_rejected_fail_closed() -> None:
    with pytest.raises(DeprecationEvidenceError, match="DUPLICATE_SCENARIO"):
        evaluate_deprecation(
            evidence=(*_all_scenarios(), _scenario(EvidenceScenario.LIVE_RUN)),
            expected_impl_head=_HEAD,
            criteria=_criteria(),
        )


def test_scenario_input_is_immutable_and_result_is_deterministic() -> None:
    evidence = _all_scenarios()
    before = deepcopy(evidence)

    left = evaluate_deprecation(
        evidence=evidence,
        expected_impl_head=_HEAD,
        criteria=_criteria(),
    )
    right = evaluate_deprecation(
        evidence=tuple(reversed(evidence)),
        expected_impl_head=_HEAD,
        criteria=_criteria(),
    )

    assert evidence == before
    assert left.to_dict() == right.to_dict()
    assert left.to_dict()["scenario_measurements"] == sorted(
        left.to_dict()["scenario_measurements"],
        key=lambda item: item["scenario"],
    )


def test_policy_has_no_external_dispatch_or_transport_surface() -> None:
    from taskcontroller.controlplane import deprecation

    source = Path(deprecation.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "requests" not in source
    assert "socket" not in source
    assert "slack" not in source.lower()
    assert "github" not in source.lower()


def test_malformed_counts_and_defect_values_fail_closed() -> None:
    with pytest.raises(DeprecationEvidenceError, match="COUNT_INVALID"):
        _scenario(EvidenceScenario.LIVE_RUN, measured=0, successful=0)

    with pytest.raises(DeprecationEvidenceError, match="COUNT_INVALID"):
        _scenario(EvidenceScenario.LIVE_RUN, measured=1, successful=2)

    with pytest.raises(DeprecationEvidenceError, match="COUNT_INVALID"):
        evaluate_deprecation(
            evidence=_all_scenarios(),
            expected_impl_head=_HEAD,
            criteria=_criteria(),
            unresolved_severity_loss_defects=-1,
        )
