"""TC-MBX-704 semantic acceptance contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.domain.models import TaskContract
from taskcontroller.domain.values import CapabilityRequirement, EvidenceSpec, ScopeSpec
from taskcontroller.execution.terminal_result import build_terminal_parent_result
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope

from taskcontroller.controlplane.semantic_acceptance import (
    SemanticAcceptanceError,
    evaluate_terminal_acceptance,
)


_FIXTURE = Path(__file__).parent / "fixtures" / "v2_contract_fixtures.json"
_DIGEST = "sha256:" + "a" * 64
_EVIDENCE = "artifact://evidence-704"
_CRITERION = "The bounded contract is satisfied with exact evidence."


def _request() -> V2MailboxEnvelope:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    return V2MailboxEnvelope.from_dict(copy.deepcopy(payload))


def _contract(*, run_id: str = "run-1", node_id: str = "node-1") -> TaskContract:
    return TaskContract(
        contract_id="contract-1",
        run_id=run_id,
        node_id=node_id,
        objective="Run one bounded semantic acceptance check.",
        scope=ScopeSpec(allowed_work=["read_repo"]),
        acceptance_criteria=[_CRITERION],
        capability_requirement=CapabilityRequirement(capability_id="taskcontroller.executor"),
        required_evidence=[
            EvidenceSpec(
                evidence_id="evidence-704",
                description="Exact terminal evidence",
                artifact_ref=_EVIDENCE,
            )
        ],
        plan_version="plan-1",
        run_version="run-version-1",
    )


def _normalized(
    *,
    status: str = "SUCCEEDED",
    criteria: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    refs = [_EVIDENCE] if evidence_refs is None else evidence_refs
    return {
        "protocol": "dw.taskcontroller.parent-synthesis/v1",
        "status": status,
        "accepted_criteria": [_CRITERION] if criteria is None else criteria,
        "findings": [
            {
                "finding_id": "finding-704",
                "severity": "info",
                "category": "acceptance",
                "lens": "controller",
                "claim": "The acceptance adapter has exact evidence.",
                "evidence_refs": refs or ["artifact://other-704"],
                "recommendation": "Retain the evidence binding.",
                "reviewer": "controller-704",
                "disposition": "ACCEPTED",
            }
        ],
        "child_refs": [
            {
                "child_id": "child-704",
                "status": "SUCCEEDED",
                "result_digest": _DIGEST,
                "normalization_digest": _DIGEST,
                "raw_output_digest": "sha256:" + "b" * 64,
                "child_contract_digest": "sha256:" + "c" * 64,
                "source_digest": "sha256:" + "d" * 64,
                "lens": "controller",
                "reviewer": "controller-704",
            }
        ],
        "residual_risks": [],
        "unresolved_questions": [],
        "conflicts": [],
        "controller_decision": {
            "decision_id": "decision-704",
            "run_ref": "run-1",
            "decision_type": "COMPLETE",
            "rationale": "The Controller has exact acceptance evidence.",
            "evidence_refs": refs,
        },
    }


def _terminal(**kwargs: Any):
    return build_terminal_parent_result(
        _request(),
        _normalized(**kwargs),
        message_id="terminal-704",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-704",
    )


def test_accepts_succeeded_terminal_only_when_contract_criteria_and_evidence_bind() -> None:
    outcome = evaluate_terminal_acceptance(_contract(), _terminal())

    assert outcome.accepted is True
    assert outcome.can_close is True
    assert outcome.result_digest == _terminal().result_digest
    assert outcome.missing_criteria == ()
    assert outcome.missing_evidence == ()
    assert _EVIDENCE in outcome.evidence_refs


def test_executor_success_with_missing_evidence_cannot_close_node() -> None:
    outcome = evaluate_terminal_acceptance(
        _contract(),
        _terminal(evidence_refs=["artifact://wrong-704"]),
    )

    assert outcome.accepted is False
    assert outcome.can_close is False
    assert outcome.missing_evidence == ("evidence-704",)
    assert "MISSING_REQUIRED_EVIDENCE" in outcome.reason_codes
    assert outcome.result_digest.startswith("sha256:")


def test_succeeded_terminal_with_missing_acceptance_criterion_cannot_close_node() -> None:
    outcome = evaluate_terminal_acceptance(_contract(), _terminal(criteria=[]))

    assert outcome.accepted is False
    assert outcome.can_close is False
    assert outcome.missing_criteria == (_CRITERION,)
    assert "MISSING_ACCEPTANCE_CRITERIA" in outcome.reason_codes


def test_non_succeeded_terminal_is_not_semantically_accepted() -> None:
    outcome = evaluate_terminal_acceptance(_contract(), _terminal(status="FAILED"))

    assert outcome.accepted is False
    assert outcome.can_close is False
    assert "TERMINAL_NOT_SUCCEEDED" in outcome.reason_codes


def test_terminal_contract_binding_mismatch_fails_closed() -> None:
    with pytest.raises(SemanticAcceptanceError) as caught:
        evaluate_terminal_acceptance(_contract(run_id="different-run"), _terminal())

    assert caught.value.code == "SEMANTIC_CONTRACT_MISMATCH"
