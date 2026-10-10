"""Anti-stuck orchestration policy tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from taskcontroller.controlplane.orchestration_policy import (
    BLOCKER_AUTHORITY_BOUNDARY,
    decide_executor_loop_continuity,
    decide_stale_authority_recovery,
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



@pytest.mark.parametrize(
    ("loop_role", "loop_run_id", "current_run_id", "expected_scheduler", "expected_next"),
    [
        ("MAILBOX_POLL", "run-current", "run-current", "PAUSE_MAILBOX_POLL_SCHEDULER", "RESOLVE_EXECUTION_AUTHORITY"),
        ("CONTROLLER_WAKEUP_POLL", "run-current", "run-current", "PAUSE_MAILBOX_POLL_SCHEDULER", "RESOLVE_EXECUTION_AUTHORITY"),
        ("MAILBOX_POLL", "run-old", "run-fresh", "QUARANTINE_STALE_LOOP", "RESOLVE_RUN_BINDING"),
        ("ENGINEERING_WORK", "run-old", "run-fresh", "QUARANTINE_STALE_LOOP", "RESOLVE_RUN_BINDING"),
    ],
)
def test_loop_pause_is_scheduler_only_not_executor_session_termination(
    loop_role: str, loop_run_id: str, current_run_id: str,
    expected_scheduler: str, expected_next: str,
) -> None:
    decision = decide_executor_loop_continuity(
        loop_role=loop_role,
        loop_run_id=loop_run_id,
        canonical_run_id=current_run_id,
        execute_contract_current=False,
    )
    assert decision.scheduler_action == expected_scheduler
    assert decision.executor_session_action in {"AWAIT_VALID_EXECUTE", "PRESERVE_EXECUTOR_SESSION"}
    assert decision.executor_session_action != "TERMINAL"
    assert decision.next_owner == "CONTROLLER"
    assert decision.typed_next == expected_next
    assert decision.effects_allowed is False
    assert decision.auto_resume_allowed is False


def test_valid_engineering_contract_continues_without_timer_or_controller_wait() -> None:
    decision = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK",
        loop_run_id="run-fresh",
        canonical_run_id="run-fresh",
        execute_contract_current=True,
    )
    assert decision.scheduler_action == "NO_AUTOMATIC_LOOP_MUTATION"
    assert decision.executor_session_action == "CONTINUE_EXECUTE"
    assert decision.typed_next == "EXECUTE_NEXT_READY_WORK"
    assert decision.next_owner == "EXECUTOR"
    assert decision.effects_allowed is True


def test_valid_contract_does_not_authorize_mailbox_poll_scheduler() -> None:
    decision = decide_executor_loop_continuity(
        loop_role="MAILBOX_POLL",
        loop_run_id="run-fresh",
        canonical_run_id="run-fresh",
        execute_contract_current=True,
    )
    assert decision.scheduler_action == "PAUSE_MAILBOX_POLL_SCHEDULER"
    assert decision.executor_session_action == "CONTINUE_EXECUTE_WITHOUT_MAILBOX_POLL"
    assert decision.effects_allowed is True


def test_waiting_for_controller_event_does_not_end_executor_session() -> None:
    decision = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK",
        loop_run_id="run-fresh",
        canonical_run_id="run-fresh",
        execute_contract_current=True,
        awaiting_controller_event=True,
    )
    assert decision.executor_session_action == "AWAIT_EVENT_DRIVEN_SUCCESSOR"
    assert decision.next_owner == "CONTROLLER"
    assert decision.typed_next == "AWAIT_VALID_CONTROLLER_EVENT"
    assert decision.effects_allowed is False
    assert decision.auto_resume_allowed is False


def test_missing_event_adapter_requires_controller_action_not_loop_poll() -> None:
    decision = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK",
        loop_run_id="run-fresh",
        canonical_run_id="run-fresh",
        execute_contract_current=True,
        awaiting_controller_event=True,
        event_adapter_qualified=False,
    )
    assert decision.executor_session_action == "AWAIT_QUALIFIED_EVENT_ADAPTER"
    assert decision.typed_next == "QUALIFY_EVENT_ADAPTER"
    assert decision.effects_allowed is False


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"hold_type": HOLD_EFFECT}, "RESOLVE_EFFECT_AUTHORITY"),
        ({"hold_type": HOLD_RUN}, "RESOLVE_RUN_HOLD"),
        ({"user_paused": True}, "RESOLVE_USER_PAUSE"),
    ],
)
def test_holds_are_distinct_from_timer_polling_suppression(kwargs: dict, expected: str) -> None:
    decision = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK",
        loop_run_id="run-current",
        canonical_run_id="run-current",
        execute_contract_current=True,
        **kwargs,
    )
    assert decision.typed_next == expected
    assert decision.effects_allowed is False
    assert decision.auto_resume_allowed is False


def test_unrelated_host_loop_is_never_mutated_or_quarantined() -> None:
    decision = decide_executor_loop_continuity(
        loop_role="UNRELATED",
        loop_run_id="someone-elses-run",
        canonical_run_id="our-run",
        execute_contract_current=False,
    )
    assert decision.scheduler_action == "NO_AUTOMATIC_LOOP_MUTATION"
    assert decision.executor_session_action == "PRESERVE_EXECUTOR_SESSION"
    assert decision.effects_allowed is False
    assert decision.auto_resume_allowed is False


def test_terminal_event_from_obsolete_loop_cannot_close_fresh_executor() -> None:
    result = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK",
        loop_run_id="run-old",
        canonical_run_id="run-fresh",
        execute_contract_current=False,
        terminal_verified=True,
    )
    assert result.scheduler_action == "QUARANTINE_STALE_LOOP"
    assert result.executor_session_action == "PRESERVE_EXECUTOR_SESSION"
    assert result.typed_next == "RESOLVE_RUN_BINDING"
    assert result.effects_allowed is False


def test_terminal_requires_explicit_verified_terminal_evidence() -> None:
    pending = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK", loop_run_id="run-current",
        canonical_run_id="run-current", execute_contract_current=False,
        terminal_verified=False,
    )
    terminal = decide_executor_loop_continuity(
        loop_role="ENGINEERING_WORK", loop_run_id="run-current",
        canonical_run_id="run-current", execute_contract_current=False,
        terminal_verified=True,
    )
    assert pending.executor_session_action != "TERMINAL"
    assert terminal.executor_session_action == "TERMINAL"


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"loop_role": "UNKNOWN"}, "LOOP_ROLE_INVALID"),
        ({"hold_type": "HOLD"}, "LOOP_HOLD_INVALID"),
        ({"execute_contract_current": "yes"}, "LOOP_CONTRACT_INVALID"),
    ],
)
def test_loop_continuity_rejects_invalid_guards(extra: dict, code: str) -> None:
    arguments = dict(
        loop_role="ENGINEERING_WORK", loop_run_id="run-current",
        canonical_run_id="run-current", execute_contract_current=False,
    )
    arguments.update(extra)
    with pytest.raises(OrchestrationPolicyError) as exc:
        decide_executor_loop_continuity(**arguments)
    assert exc.value.code == code


@pytest.mark.parametrize(
    ("approval_current", "lease_current", "route", "expected", "request"),
    [
        (True, False, "HUMAN", "ISSUE_FRESH_ATTEMPT_LEASE", False),
        (True, True, "HUMAN", "CONTINUE_WITH_CURRENT_FENCE", False),
        (False, False, "HUMAN", "MATERIALIZE_HUMAN_APPROVAL_REQUEST", True),
        (False, False, "DELEGATE", "DISPATCH_DELEGATED_AUTHORITY_REQUEST", True),
        (False, False, "NONE", "AUTHORITY_REQUEST_UNROUTED", True),
    ],
)
def test_stale_authority_recovery_distinguishes_lease_from_approval(
    approval_current: bool, lease_current: bool, route: str, expected: str, request: bool,
) -> None:
    resolution = decide_stale_authority_recovery(
        current_run_id="fresh-run", observed_event_run_id="fresh-run",
        approval_current=approval_current, execution_lease_current=lease_current,
        renewal_route=route,
    )
    assert resolution.next_action == expected
    assert resolution.approval_request_required is request
    assert resolution.protected_effects_allowed is False
    assert resolution.next_owner == "CONTROLLER"


def test_historical_e9_cannot_be_replayed_as_fresh_authority() -> None:
    decision = decide_stale_authority_recovery(
        current_run_id="scrum781-q0-fresh-20261010-r1",
        observed_event_run_id="scrum781-q0-20260920T074727Z",
        approval_current=True, execution_lease_current=True, renewal_route="HUMAN",
    )
    assert decision.next_action == "RECOVER_CURRENT_RUN_BINDING"
    assert decision.rejected_historical_run_id == "scrum781-q0-20260920T074727Z"
    assert decision.protected_effects_allowed is False


@pytest.mark.parametrize(("hold", "paused", "next_action"), [
    (True, False, "RESOLVE_RUN_HOLD"),
    (False, True, "RESOLVE_USER_PAUSE"),
])
def test_expired_authority_never_bypasses_explicit_run_hold(
    hold: bool, paused: bool, next_action: str,
) -> None:
    decision = decide_stale_authority_recovery(
        current_run_id="fresh-run", observed_event_run_id="fresh-run",
        approval_current=False, execution_lease_current=False,
        renewal_route="HUMAN", run_hold=hold, user_paused=paused,
    )
    assert decision.next_action == next_action
    assert decision.approval_request_required is False


def test_authority_recovery_rejects_unrecognized_route() -> None:
    with pytest.raises(OrchestrationPolicyError) as exc:
        decide_stale_authority_recovery(
            current_run_id="fresh-run", observed_event_run_id="fresh-run",
            approval_current=False, execution_lease_current=False,
            renewal_route="AUTO_APPROVE",
        )
    assert exc.value.code == "AUTHORITY_ROUTE_INVALID"
