"""Regression: Controller-native bootstrap is not blocked on Executor dispatch readiness.

Real TaskController admission/contracting is verified here. Project-specific native
gate ownership and gate receipts still come from the active project's runtime;
TaskController must not invent a second gate engine or weaken dispatch safety.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from taskcontroller.controlplane.execution_contracting import validate_execution_contracting
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp.activation import resolve_taskcontroller_activation

ROOT = Path(__file__).resolve().parents[2]


def _content(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


@pytest.mark.parametrize("executor", [None, "hermes mac", "hermes cloud"])
def test_fresh_controller_bootstrap_does_not_require_executor_session(executor):
    plan = resolve_taskcontroller_activation(
        "TaskController: start a fresh governed Controller plan",
        host="chatgpt", executor=executor,
    )
    assert plan.active is True
    assert plan.controller_only_progress_allowed_without_executor is True
    assert plan.mailbox_boot_boundary == "first_executor_dispatch"
    assert plan.mailbox_boot_required is True
    assert plan.mailbox_boot_fail_closed is True
    assert plan.interaction_protocol == "dw.taskcontroller.mailbox/v2"
    # Source-load activation is not a claim that mailbox event/continuation exists.


def test_inactive_resolver_does_not_claim_controller_bootstrap():
    plan = resolve_taskcontroller_activation("write a poem", host="chatgpt")
    assert plan.active is False
    assert plan.controller_only_progress_allowed_without_executor is False
    assert plan.mailbox_boot_boundary is None


def test_controller_owned_readonly_plan_does_not_need_executor_or_lease():
    receipt = validate_execution_contracting(
        payload={"controller_contract_mode": "PLAN", "execution_authority_active": False},
        scope={
            "allowed_actions": ["read_exact_source"],
            "denied_actions": ["modify_approved_files", "merge_approved_pr", "deploy_approved_release"],
            "writable_targets": [],
        },
    )
    assert receipt.mode == "PLAN"
    assert receipt.real_work_required is False
    assert receipt.authority_granted is False


def test_first_executor_dispatch_still_fails_without_effect_authority():
    with pytest.raises(TaskControllerValidationError, match="already-validated bounded execution authority"):
        validate_execution_contracting(
            payload={"controller_contract_mode": "EXECUTE", "execution_authority_active": False},
            scope={
                "allowed_actions": ["modify_approved_files"],
                "denied_actions": ["merge_approved_pr", "deploy_approved_release"],
                "writable_targets": ["taskcontroller"],
            },
        )


def test_registry_scopes_mailbox_materialization_to_first_executor_dispatch():
    registry = _content("controllers/taskcontroller.yaml")
    assert "controller_first_bootstrap:" in registry
    assert "native_controller_owned_gates_allowed_without_executor: true" in registry
    assert "controller_only_gate_requires_mailbox_event: false" in registry
    assert "native_receipt_validation_required: true" in registry
    assert "run_hold_remains_binding: true" in registry
    assert "applies_to: first-executor-dispatch" in registry
    assert "controller_only_progress_requires_mailbox_boot: false" in registry
    assert "before_first_dispatch: true" in registry
    assert "continuation_required: true" in registry
    assert "exact_readback_required: true" in registry
    assert "periodic_mailbox_polling: forbidden" in registry


def test_chatgpt_and_root_instructions_do_not_block_native_controller_gates():
    overlay = _content("agents/chatgpt-agent/agent-instructions.md")
    root = _content("AGENTS.md")
    assert "**Controller-native bootstrap/activation:**" in overlay
    assert "**First Executor dispatch readiness:**" in overlay
    assert "Until the first actual dispatch, mailbox materialization is not a prerequisite" in overlay
    assert "The Executor's own PRECHECK occurs **after receipt**" in overlay
    assert "Controller-first bootstrap boundary" in root
    assert "it does **not** require an Executor session" in root


def test_native_controller_phase_precedes_a2a_executor_boot_not_old_mutable_comment():
    protocol = _content("agents/shared/taskcontroller-a2a-protocol.md")
    bootstrap = protocol.split("## Legacy v1 compatibility mailbox model", 1)[0]
    assert "## Session boot — Controller-owned gates before Executor dispatch" in bootstrap
    assert "native materialize_controller_transition (persist continuation first)" in bootstrap
    assert "Executor performs its own PRECHECK on received command" in bootstrap
    assert "A missing Executor session" in bootstrap
    assert "updated in place" not in bootstrap
    assert "poll exact Executor mailbox comment only" not in bootstrap
    assert "Do not issue a placeholder execution request" in bootstrap


def test_hermes_runbook_precheck_is_executor_only():
    runbook = _content("docs/runbooks/HERMES_DESKTOP_RUNTIME.md")
    slack = _content("agents/chatgpt-agent/slack-controller-mvp.md")
    assert "## Controller-first bootstrap boundary (not an Executor PRECHECK)" in runbook
    assert "does not gate Controller-only planning" in runbook
    assert "Controller-native bootstrap and Controller-owned gate progression" in slack
    assert "before the **first actual Executor dispatch**" in slack
    assert "block dispatch only" in slack



def test_loop_scheduler_is_not_a_terminal_executor_or_run_hold():
    controller = _content("agents/chatgpt-agent/agent-instructions.md")
    hermes = _content("agents/hermes/agent-instructions.md")
    runbook = _content("docs/runbooks/HERMES_DESKTOP_RUNTIME.md")
    shared = _content("agents/shared/taskcontroller-a2a-protocol.md")
    root = _content("AGENTS.md")
    registry = _content("controllers/taskcontroller.yaml")
    assert "decide_executor_loop_continuity()" in controller
    assert "Host `LoopManager` scheduler state is separate" in hermes
    assert "scheduler row is not" in runbook
    assert "forbidden polling scheduler is not a stopped Executor session" in shared
    assert "Hermes Loop continuity" in root
    assert "pure_decision_guard: taskcontroller/controlplane/orchestration_policy.py::decide_executor_loop_continuity" in registry
    assert "host_pause_implies_run_hold: false" in registry
    assert "host_pause_implies_terminal: false" in registry
    assert "policy_guard_mutates_host_scheduler: false" in registry


def test_hermes_runbook_has_no_default_old_run_recovery_command():
    runbook = _content("docs/runbooks/HERMES_DESKTOP_RUNTIME.md")
    assert "--issue 575" not in runbook
    assert "--run-id scrum781-q0-20260920T074727Z" not in runbook
    assert "do not keep, re-arm, or resume **that forbidden polling scheduler**" in runbook
    assert "live canonical Controller mailbox/continuation" in runbook
    assert "Do not attribute a pause/resume to a user without an actor-bearing event" in runbook
