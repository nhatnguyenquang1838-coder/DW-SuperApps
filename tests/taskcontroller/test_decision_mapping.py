"""TC-MBX-705 normalized-result decision mapping tests."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.controlplane.semantic_acceptance import evaluate_terminal_acceptance
from taskcontroller.domain.models import TaskContract
from taskcontroller.domain.values import CapabilityRequirement, EvidenceSpec, ScopeSpec
from taskcontroller.execution.terminal_result import build_terminal_parent_result
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope

from taskcontroller.controlplane.decision_mapping import (
    DecisionMappingError,
    map_terminal_decision,
)


_FIXTURE = Path(__file__).parent / "fixtures" / "v2_contract_fixtures.json"
_CHILD_DIGEST = "sha256:" + "a" * 64
_EVIDENCE = "artifact://evidence-705"
_CRITERION = "The bounded decision has exact evidence."


def _request() -> V2MailboxEnvelope:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    return V2MailboxEnvelope.from_dict(copy.deepcopy(payload))


def _contract() -> TaskContract:
    return TaskContract(
        contract_id="contract-1",
        run_id="run-1",
        node_id="node-1",
        objective="Map one normalized result.",
        scope=ScopeSpec(allowed_work=["read_repo"]),
        acceptance_criteria=[_CRITERION],
        capability_requirement=CapabilityRequirement(capability_id="taskcontroller.executor"),
        required_evidence=[
            EvidenceSpec(
                evidence_id="evidence-705",
                description="Exact decision evidence",
                artifact_ref=_EVIDENCE,
            )
        ],
        plan_version="plan-1",
        run_version="run-version-1",
    )


def _normalized(
    *,
    decision_type: str = "COMPLETE",
    criteria: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    status: str = "SUCCEEDED",
) -> dict[str, Any]:
    refs = [_EVIDENCE] if evidence_refs is None else evidence_refs
    return {
        "protocol": "dw.taskcontroller.parent-synthesis/v1",
        "status": status,
        "accepted_criteria": [_CRITERION] if criteria is None else criteria,
        "findings": [
            {
                "finding_id": "finding-705",
                "severity": "info",
                "category": "decision",
                "lens": "controller",
                "claim": "The decision has exact evidence.",
                "evidence_refs": refs or ["artifact://other-705"],
                "recommendation": "Retain the decision evidence.",
                "reviewer": "controller-705",
                "disposition": "ACCEPTED",
            }
        ],
        "child_refs": [
            {
                "child_id": "child-705",
                "status": "SUCCEEDED",
                "result_digest": _CHILD_DIGEST,
                "normalization_digest": _CHILD_DIGEST,
                "raw_output_digest": "sha256:" + "b" * 64,
                "child_contract_digest": "sha256:" + "c" * 64,
                "source_digest": "sha256:" + "d" * 64,
                "lens": "controller",
                "reviewer": "controller-705",
            }
        ],
        "residual_risks": [],
        "unresolved_questions": [],
        "conflicts": [],
        "controller_decision": {
            "decision_id": "decision-705",
            "run_ref": "run-1",
            "decision_type": decision_type,
            "rationale": "The Controller has the normalized evidence.",
            "evidence_refs": refs,
        },
    }


def _terminal(**kwargs: Any):
    return build_terminal_parent_result(
        _request(),
        _normalized(**kwargs),
        message_id="terminal-705",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-705",
    )


def _acceptance(terminal):
    return evaluate_terminal_acceptance(_contract(), terminal)


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("CONTINUE", "CONTINUE"),
        ("RETRY", "RETRY"),
        ("REPLAN", "REPLAN"),
        ("WAIT", "WAIT"),
        ("ESCALATE", "ESCALATE"),
        ("COMPLETE", "COMPLETE"),
    ],
)
def test_maps_normalized_decision_and_retains_digest_and_evidence(
    requested: str, expected: str
) -> None:
    terminal = _terminal(decision_type=requested)
    mapping = map_terminal_decision(terminal, _acceptance(terminal))

    assert mapping.decision == expected
    assert mapping.requested_decision == requested
    assert mapping.decision_id == "decision-705"
    assert mapping.result_digest == terminal.result_digest
    assert mapping.evidence_refs == (_EVIDENCE,)
    assert mapping.authority_granted is False


def test_complete_is_downgraded_to_wait_when_semantic_acceptance_is_false() -> None:
    terminal = _terminal(evidence_refs=["artifact://wrong-705"])
    mapping = map_terminal_decision(terminal, _acceptance(terminal))

    assert mapping.requested_decision == "COMPLETE"
    assert mapping.decision == "WAIT"
    assert mapping.completion_blocked is True
    assert "COMPLETION_NOT_ACCEPTED" in mapping.reason_codes
    assert mapping.result_digest == terminal.result_digest
    assert mapping.evidence_refs == ("artifact://wrong-705",)


def test_cancel_remains_a_human_boundary_and_maps_to_escalate() -> None:
    terminal = _terminal(decision_type="CANCEL")
    mapping = map_terminal_decision(terminal, _acceptance(terminal))

    assert mapping.requested_decision == "CANCEL"
    assert mapping.decision == "ESCALATE"
    assert mapping.human_approval_required is True
    assert mapping.authority_granted is False
    assert "HUMAN_AUTHORITY_REQUIRED" in mapping.reason_codes


def test_acceptance_result_digest_mismatch_fails_closed() -> None:
    terminal = _terminal()
    acceptance = _acceptance(terminal)

    with pytest.raises(DecisionMappingError) as caught:
        map_terminal_decision(
            terminal,
            replace(acceptance, result_digest="sha256:" + "f" * 64),
        )

    assert caught.value.code == "DECISION_RESULT_DIGEST_MISMATCH"


def test_unknown_requested_decision_fails_closed() -> None:
    terminal = _terminal(decision_type="UNKNOWN")

    with pytest.raises(DecisionMappingError) as caught:
        map_terminal_decision(terminal, _acceptance(terminal))

    assert caught.value.code == "DECISION_INVALID"
