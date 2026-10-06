"""Anti-stuck orchestration policy tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from taskcontroller.controlplane.orchestration_policy import (
    BLOCKER_AUTHORITY_BOUNDARY,
    HOLD_EFFECT,
    HOLD_RUN,
    OrchestrationPolicyError,
    validate_executor_progress,
    validate_hold_semantics,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest


_FIXTURE = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"


def _progress(
    *,
    status: str = "SUCCEEDED",
    typed_next: str | None = "COMPLETE",
    blocker_class: str | None = None,
    blocker_detail: str | None = None,
    extra_payload: dict[str, object] | None = None,
) -> V2MailboxEnvelope:
    payload = copy.deepcopy(
        json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    )
    payload["message_id"] = "progress-policy-1"
    payload["seq"] = 1
    payload["direction"] = "executor_to_controller"
    payload["message_type"] = "execution_progress"
    payload["producer"] = {
        "namespace": "executor",
        "actor_id": "hermes",
        "role": "executor",
    }
    payload["recipient"] = {
        "capability": "taskcontroller.controller",
        "agent_instance": "controller",
    }
    progress_payload: dict[str, object] = {
        "status": status,
        "report_type": "mission_status",
    }
    if typed_next is not None:
        progress_payload["typed_next"] = typed_next
    if blocker_class is not None:
        progress_payload["blocker_class"] = blocker_class
    if blocker_detail is not None:
        progress_payload["blocker_detail"] = blocker_detail
    if extra_payload:
        progress_payload.update(extra_payload)
    payload["payload"] = progress_payload
    provenance_status = (
        "SUCCEEDED"
        if status == "SUCCEEDED"
        else "NEEDS_CLARIFICATION"
        if status in {"BLOCKED", "NEEDS_CLARIFICATION"}
        else "RUNNING"
    )
    payload["provenance"] = {
        "origin": "executor",
        "parent_message_id": "request-1",
        "child_id": None,
        "lens": "execution",
        "agent_instance": "hermes",
        "status": provenance_status,
        "source_refs": [],
        "evidence_refs": [],
        "result_digest": None,
    }
    payload["idempotency_key"] = "progress-policy-idem-1"
    payload.pop("result", None)
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def test_success_progress_returns_to_controller_without_user_wait() -> None:
    outcome = validate_executor_progress(_progress())

    assert outcome.completed is True
    assert outcome.requires_controller_action is False
    assert outcome.blocker_class is None


def test_blocked_progress_requires_one_canonical_blocker_class() -> None:
    with pytest.raises(OrchestrationPolicyError) as error:
        validate_executor_progress(
            _progress(status="BLOCKED", typed_next="WAIT_CONTROLLER")
        )
    assert error.value.code == "EXECUTOR_BLOCKER_CLASS_REQUIRED"

    outcome = validate_executor_progress(
        _progress(
            status="BLOCKED",
            typed_next="WAIT_CONTROLLER",
            blocker_class=BLOCKER_AUTHORITY_BOUNDARY,
            blocker_detail="G3_PR authority is outside the active mission ceiling.",
        )
    )
    assert outcome.requires_controller_action is True
    assert outcome.blocker_class == BLOCKER_AUTHORITY_BOUNDARY


@pytest.mark.parametrize("typed_next", ["WAIT_USER_G2_APPROVAL", "WAIT_HUMAN_APPROVAL"])
def test_executor_cannot_wait_for_user_or_human_directly(typed_next: str) -> None:
    with pytest.raises(OrchestrationPolicyError) as error:
        validate_executor_progress(
            _progress(
                status="BLOCKED",
                typed_next=typed_next,
                blocker_class=BLOCKER_AUTHORITY_BOUNDARY,
                blocker_detail="Authority boundary reached.",
            )
        )
    assert error.value.code == "EXECUTOR_USER_HITL_FORBIDDEN"


def test_executor_cannot_materialize_human_approval_command() -> None:
    with pytest.raises(OrchestrationPolicyError) as error:
        validate_executor_progress(
            _progress(extra_payload={"approval_command": "APPROVE G2 something"})
        )
    assert error.value.code == "EXECUTOR_USER_HITL_FORBIDDEN"


def test_effect_hold_gates_effects_but_keeps_control_loop_running() -> None:
    hold = validate_hold_semantics(
        {
            "hold": {
                "type": HOLD_EFFECT,
                "denied_effects": ["git_write", "repo_write"],
                "control_loop_continues": True,
            }
        }
    )

    assert hold is not None
    assert hold.hold_type == HOLD_EFFECT
    assert hold.control_loop_continues is True


def test_run_hold_is_the_only_hold_that_stops_control_loop() -> None:
    hold = validate_hold_semantics(
        {
            "hold": {
                "type": HOLD_RUN,
                "denied_effects": [],
                "control_loop_continues": False,
            }
        }
    )

    assert hold is not None
    assert hold.hold_type == HOLD_RUN
    assert hold.control_loop_continues is False


def test_ambiguous_hold_disposition_is_rejected() -> None:
    with pytest.raises(OrchestrationPolicyError) as error:
        validate_hold_semantics({"disposition": "HOLD_CURRENT_USER_DENIAL"})
    assert error.value.code == "AMBIGUOUS_HOLD_FORBIDDEN"


def test_effect_hold_cannot_stop_the_controller_control_loop() -> None:
    with pytest.raises(OrchestrationPolicyError) as error:
        validate_hold_semantics(
            {
                "hold": {
                    "type": HOLD_EFFECT,
                    "denied_effects": ["git_write"],
                    "control_loop_continues": False,
                }
            }
        )
    assert error.value.code == "EFFECT_HOLD_MUST_CONTINUE_CONTROL_LOOP"
