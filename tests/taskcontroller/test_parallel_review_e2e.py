"""TC-MBX-1002: deterministic out-of-order multi-lens Mixer E2E."""

from __future__ import annotations

import json

from taskcontroller.controlplane.execution_boundary import ExecutionBoundary
from taskcontroller.domain.enums import DecisionType, ReviewVerdict
from taskcontroller.execution.child_contract import (
    ChildContractInput,
    ParentContract,
    generate_child_contracts,
)
from taskcontroller.execution.fanout import (
    ChildCompletion,
    CompletionStatus,
    FanoutCoordinator,
    FanoutMode,
    JoinStatus,
    child_completion,
)
from taskcontroller.execution.parent_synthesis import (
    ControllerDecision,
    synthesize_parent_result,
)
from taskcontroller.execution.result_normalizer import ChildResultNormalizer
from taskcontroller.interaction.mailbox_v2 import SOURCE_MANIFEST_VERSION


_PARENT_DIGEST = "sha256:" + "1" * 64
_SOURCE_DIGEST = "sha256:" + "2" * 64
_STANDARDS_DIGEST = "sha256:" + "3" * 64
_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "1" * 40,
    "path": "AGENTS.md",
    "blob_digest": "sha256:" + "4" * 64,
}


def _parent() -> ParentContract:
    return ParentContract(
        run_id="run-1002",
        node_id="node-1002",
        contract_id="contract-1002",
        contract_digest=_PARENT_DIGEST,
        plan_version="plan-1002",
        boundary=ExecutionBoundary(
            allowed_actions=("read_repo", "write_artifact"),
            denied_actions=("deploy", "merge"),
            writable_targets=("artifacts/review/**",),
            source_roots=("src",),
            max_children=3,
            max_parallel=3,
            max_depth=1,
            replan_required_when=("scope_expansion", "budget_exceeded"),
        ),
        source_digest=_SOURCE_DIGEST,
        source_manifest_ref="manifest-1002",
        source_manifest={
            "manifest_version": SOURCE_MANIFEST_VERSION,
            "digest": _SOURCE_DIGEST,
            "sources": [_SOURCE],
        },
        standards_profile_ref="standards.default/v1",
        standards_profile={
            "profile_id": "standards.default",
            "version": "v1",
            "digest": _STANDARDS_DIGEST,
        },
        objective="Run three bounded independent review lenses.",
        acceptance_criteria=(
            "Every required child completion is represented.",
            "The normalized parent result is deterministic.",
            "Every finding retains child evidence provenance.",
        ),
        agent_instance="hermes-mac",
    )


def _children() -> tuple:
    parent = _parent()
    child_boundary = ExecutionBoundary(
        allowed_actions=("read_repo",),
        denied_actions=("deploy", "merge"),
        writable_targets=("artifacts/review/**",),
        source_roots=("src",),
        max_children=1,
        max_parallel=1,
        max_depth=0,
        replan_required_when=("scope_expansion", "budget_exceeded"),
    )
    return generate_child_contracts(
        parent,
        [
            ChildContractInput(
                child_id=f"child-{index}",
                lens=lens,
                boundary=child_boundary,
                objective=f"Inspect the {lens} lens.",
                acceptance_criteria=(parent.acceptance_criteria[0],),
            )
            for index, lens in enumerate(
                ("architecture", "security", "reliability"),
                start=1,
            )
        ],
    )


def _completion(child) -> ChildCompletion:
    suffix = child.child_id.rsplit("-", 1)[-1]
    return child_completion(
        child_id=child.child_id,
        child_contract_digest=child.contract_digest,
        status=CompletionStatus.SUCCEEDED,
        result_ref=f"github://result/run-1002/{child.child_id}",
        result_digest="sha256:" + suffix * 64,
    )


def _normalized(child):
    reviewer = f"reviewer-{child.child_id.rsplit('-', 1)[-1]}"
    normalizer = ChildResultNormalizer(
        child_id=child.child_id,
        child_contract_digest=child.contract_digest,
        source_digest=_SOURCE_DIGEST,
        lens=child.lens,
        reviewer=reviewer,
    )
    return normalizer.normalize(
        {
            "findings": [
                {
                    "finding_id": f"finding-{child.child_id}",
                    "severity": "minor",
                    "category": "boundary",
                    "lens": child.lens,
                    "claim": f"{child.lens} boundary is observable",
                    "evidence_refs": [f"evidence://run-1002/{child.child_id}"],
                    "recommendation": f"Retain the {child.lens} evidence reference",
                    "reviewer": reviewer,
                    "disposition": "OPEN",
                }
            ]
        }
    )


def _decision() -> ControllerDecision:
    return ControllerDecision(
        decision_id="decision-1002",
        run_ref="run-1002",
        decision_type=DecisionType.COMPLETE,
        rationale="Controller decision is bound to the normalized multi-lens evidence.",
        evidence_refs=("evidence://run-1002/mixer",),
    )


def _run_e2e(completion_order: tuple[int, ...], mixer_order: tuple[int, ...]):
    children = _children()
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode=FanoutMode.PARALLEL,
        max_parallel=3,
    )
    assert coordinator.dispatch_window() == ("child-1", "child-2", "child-3")

    for index in completion_order:
        coordinator = coordinator.complete(_completion(children[index]))

    joined = coordinator.join()
    assert joined.status is JoinStatus.READY
    assert joined.normalized_input is not None
    assert joined.normalized_input.child_ids == ("child-1", "child-2", "child-3")

    normalized = tuple(_normalized(children[index]) for index in mixer_order)
    result = synthesize_parent_result(
        normalized,
        proposed_verdict=ReviewVerdict.PASS,
        controller_decision=_decision(),
    )
    return result


def test_three_children_complete_out_of_order_and_mixer_is_byte_deterministic() -> None:
    out_of_order = _run_e2e((2, 0, 1), (1, 2, 0))
    ordered = _run_e2e((0, 1, 2), (2, 0, 1))

    assert out_of_order.to_dict() == ordered.to_dict()
    payload = out_of_order.to_dict()
    assert out_of_order.final_verdict is ReviewVerdict.PASS
    assert [ref.child_id for ref in out_of_order.child_refs] == [
        "child-1",
        "child-2",
        "child-3",
    ]
    assert len(out_of_order.child_refs) == 3
    assert len(out_of_order.findings) == 3
    assert {finding.representative.reviewer for finding in out_of_order.findings} == {
        "reviewer-1",
        "reviewer-2",
        "reviewer-3",
    }
    assert all(finding.provenance_count == 1 for finding in out_of_order.findings)
    assert all(
        finding.representative.evidence_refs[0].startswith("evidence://run-1002/child-")
        for finding in out_of_order.findings
    )
    assert all(ref.result_digest.startswith("sha256:") for ref in out_of_order.child_refs)
    assert payload["result_digest"] == out_of_order.result_digest
    assert json.dumps(payload, sort_keys=True) == json.dumps(ordered.to_dict(), sort_keys=True)


def test_mixer_input_retains_each_child_contract_and_source_binding() -> None:
    result = _run_e2e((1, 2, 0), (0, 1, 2))

    expected_contract_digests = {child.child_id: child.contract_digest for child in _children()}
    assert {
        ref.child_id: ref.child_contract_digest
        for ref in result.child_refs
    } == expected_contract_digests
    assert all(ref.source_digest == _SOURCE_DIGEST for ref in result.child_refs)
    assert {finding.representative.lens for finding in result.findings} == {
        "architecture",
        "security",
        "reliability",
    }
