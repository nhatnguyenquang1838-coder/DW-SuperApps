"""WP1 DONE acceptance policy: evaluate_done_acceptance (exact binding, subset evidence/criteria).

Binding rule per WP1 R2/R3:
- verdict == PASS
- target_ref == node.contract_ref OR target_ref in node.artifact_refs (exact)
- contract.required_evidence.evidence_id ⊆ review.evidence_refs
- contract.acceptance_criteria ⊆ review.criteria (exact item equality; extras allowed)
- plan_version == contract.plan_version, run_version == contract.run_version

Rejection cases:
- no PASS review
- PASS review with wrong target_ref (not contract_ref, not in artifact_refs)
- PASS review with insufficient evidence (missing required evidence id)
- PASS review with insufficient criteria (missing acceptance_criteria item)
- PASS review with mismatched plan_version
- PASS review with mismatched run_version
- REVIEWING node without any binding review must raise (function is used to gate
  REVIEWING -> DONE at the transition boundary: no exact-binding PASS review ->
  ReviewNotBinding raised, transition rejected)
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import ReviewVerdict, NodeStatus
from taskcontroller.domain.models import ReviewResult, TaskContract
from taskcontroller.domain.values import NodeState
from taskcontroller.kernel.errors import ReviewNotBinding
from taskcontroller.kernel.policy import evaluate_done_acceptance


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_contract(task_contract):
    """WP0 task_contract fixture with 1 required evidence + 1 acceptance criterion."""
    return task_contract


@pytest.fixture
def done_node(base_contract):
    return NodeState(
        status=NodeStatus.REVIEWING.value,
        contract_ref=base_contract.contract_id,
        artifact_refs=["art.produced"],
    )


# ---------------------------------------------------------------------------
# valid binding cases
# ---------------------------------------------------------------------------


def test_exact_binding_via_contract_ref(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    result = evaluate_done_acceptance(base_contract, done_node, reviews)
    assert result.review_id == "rev.1"


def test_exact_binding_via_artifact_ref(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref="art.produced",
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    result = evaluate_done_acceptance(base_contract, done_node, reviews)
    assert result.review_id == "rev.1"


def test_exact_binding_with_extra_evidence_allowed(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[
                e.evidence_id for e in base_contract.required_evidence
            ] + ["ev.extra.1", "ev.extra.2"],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    result = evaluate_done_acceptance(base_contract, done_node, reviews)
    assert result.review_id == "rev.1"


def test_exact_binding_with_extra_criteria_allowed(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria) + ["extra.criterion"],
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    result = evaluate_done_acceptance(base_contract, done_node, reviews)
    assert result.review_id == "rev.1"


def test_exact_binding_with_both_extras_allowed(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria) + ["extra.c"],
            evidence_refs=[
                e.evidence_id for e in base_contract.required_evidence
            ] + ["ev.extra"],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    result = evaluate_done_acceptance(base_contract, done_node, reviews)
    assert result.review_id == "rev.1"


def test_binding_picks_first_matching_review_not_last(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
        ReviewResult(
            review_id="rev.2",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.2",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    result = evaluate_done_acceptance(base_contract, done_node, reviews)
    assert result.review_id == "rev.1"


# ---------------------------------------------------------------------------
# rejection cases
# ---------------------------------------------------------------------------


def test_no_pass_review_raises(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.FAIL.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_wrong_target_ref_not_binding(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref="wrong.ref",
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_insufficient_evidence_missing_required_id(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=["ev.wrong"],  # required_evidence id is ev.1, not ev.wrong
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_insufficient_criteria_missing_acceptance_item(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=["wrong.criterion"],  # acceptance_criteria is ["artifact produced"]
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_mismatched_plan_version_rejected(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version="p2",  # contract has p1
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_mismatched_run_version_rejected(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version="r2",  # contract has r1
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_empty_review_list_raises(base_contract, done_node):
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, [])


def test_multiple_reviews_only_one_binds(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref="wrong.ref",
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
        ReviewResult(
            review_id="rev.2",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.2",
            criteria=["wrong.c"],
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
        ReviewResult(
            review_id="rev.3",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.3",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=["ev.wrong"],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_failling_review_does_not_bind(base_contract, done_node):
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref=base_contract.contract_id,
            verdict=ReviewVerdict.FAIL.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, done_node, reviews)


def test_empty_artifact_refs_node_with_artifact_target_ref_fails(base_contract):
    node = NodeState(
        status=NodeStatus.REVIEWING.value,
        contract_ref=base_contract.contract_id,
        artifact_refs=[],  # empty — target_ref "art.produced" not bound
    )
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref="art.produced",
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=list(base_contract.acceptance_criteria),
            evidence_refs=[e.evidence_id for e in base_contract.required_evidence],
            plan_version=base_contract.plan_version,
            run_version=base_contract.run_version,
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(base_contract, node, reviews)


def test_exact_evidence_id_match_with_multiple_required_evidence():
    from taskcontroller.domain.values import EvidenceSpec

    contract = TaskContract(
        contract_id="tc.2",
        run_id="run.1",
        node_id="n1",
        objective="x",
        scope=__import__("taskcontroller.domain.values", fromlist=["ScopeSpec"]).ScopeSpec(
            allowed_work=["build"]
        ),
        acceptance_criteria=["c1", "c2"],
        capability_requirement=__import__(
            "taskcontroller.domain.values", fromlist=["CapabilityRequirement"]
        ).CapabilityRequirement(capability_id="cap.build"),
        plan_version="p1",
        run_version="r1",
        required_evidence=[
            EvidenceSpec(evidence_id="ev.1", description="log"),
            EvidenceSpec(evidence_id="ev.2", description="report"),
        ],
        dependencies=[],
    )
    node = NodeState(
        status=NodeStatus.REVIEWING.value,
        contract_ref="tc.2",
        artifact_refs=[],
    )
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref="tc.2",
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=["c1", "c2"],
            evidence_refs=["ev.1", "ev.2"],
            plan_version="p1",
            run_version="r1",
        ),
    ]
    result = evaluate_done_acceptance(contract, node, reviews)
    assert result.review_id == "rev.1"


def test_partial_evidence_coverage_fails_with_multiple_required():
    from taskcontroller.domain.values import EvidenceSpec

    contract = TaskContract(
        contract_id="tc.3",
        run_id="run.1",
        node_id="n1",
        objective="x",
        scope=__import__("taskcontroller.domain.values", fromlist=["ScopeSpec"]).ScopeSpec(
            allowed_work=["build"]
        ),
        acceptance_criteria=["c1"],
        capability_requirement=__import__(
            "taskcontroller.domain.values", fromlist=["CapabilityRequirement"]
        ).CapabilityRequirement(capability_id="cap.build"),
        plan_version="p1",
        run_version="r1",
        required_evidence=[
            EvidenceSpec(evidence_id="ev.1", description="log"),
            EvidenceSpec(evidence_id="ev.2", description="report"),
        ],
        dependencies=[],
    )
    node = NodeState(
        status=NodeStatus.REVIEWING.value,
        contract_ref="tc.3",
        artifact_refs=[],
    )
    reviews = [
        ReviewResult(
            review_id="rev.1",
            target_ref="tc.3",
            verdict=ReviewVerdict.PASS.value,
            reviewer="human.1",
            criteria=["c1"],
            evidence_refs=["ev.1"],  # ev.2 missing
            plan_version="p1",
            run_version="r1",
        ),
    ]
    with pytest.raises(ReviewNotBinding):
        evaluate_done_acceptance(contract, node, reviews)