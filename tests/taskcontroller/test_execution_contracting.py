from __future__ import annotations

import pytest

from taskcontroller.controlplane.execution_contracting import (
    CONTRACT_MODE_EXECUTE,
    CONTRACT_MODE_PLAN,
    CONTRACT_MODE_TRANSPORT_REPAIR,
    validate_execution_contracting,
)
from taskcontroller.errors import TaskControllerValidationError


def _scope(**changes):
    value = {
        "allowed_actions": ["read_exact_source"],
        "denied_actions": ["merge_approved_pr", "deploy_approved_release"],
        "writable_targets": [],
        "source_roots": ["taskcontroller"],
        "max_children": 0,
        "max_parallel": 1,
        "max_depth": 0,
    }
    value.update(changes)
    return value


def _execute_payload(**changes):
    value = {
        "controller_contract_mode": CONTRACT_MODE_EXECUTE,
        "execution_authority_active": True,
        "execution_plan_ref": "artifact://plan/approved-v1",
        "approval_ref": "approval://G2/123",
        "approval_digest": "sha256:" + "a" * 64,
        "work_packages": [
            {"id": "T1", "objective": "Implement the approved change."},
            {"id": "T2", "objective": "Run tests and fix failures."},
        ],
        "continue_until": ["ALL_ACCEPTANCE_CRITERIA_PASS", "DRAFT_PR_READY"],
        "stop_conditions": [
            "SOURCE_OR_BASE_DRIFT",
            "WRITE_SCOPE_EXPANSION_REQUIRED",
            "DESTRUCTIVE_OR_PRODUCTION_AUTHORITY_REQUIRED",
            "APPROVED_PLAN_PROVEN_INVALID",
        ],
    }
    value.update(changes)
    return value


def test_legacy_request_without_mode_remains_compatible():
    receipt = validate_execution_contracting(payload={}, scope=_scope())

    assert receipt.mode == "COMPATIBILITY"
    assert receipt.real_work_required is False
    assert receipt.authority_granted is False


@pytest.mark.parametrize("mode", [CONTRACT_MODE_PLAN, CONTRACT_MODE_TRANSPORT_REPAIR])
def test_readonly_modes_reject_execution_authority_and_mutation(mode):
    with pytest.raises(TaskControllerValidationError, match="must not claim active execution authority"):
        validate_execution_contracting(
            payload={"controller_contract_mode": mode, "execution_authority_active": True},
            scope=_scope(),
        )

    with pytest.raises(TaskControllerValidationError, match="cannot include real-work mutation actions"):
        validate_execution_contracting(
            payload={"controller_contract_mode": mode},
            scope=_scope(
                allowed_actions=["read_exact_source", "modify_approved_files"],
                writable_targets=["taskcontroller"],
            ),
        )


def test_execute_rejects_readonly_pseudo_g2_contract():
    with pytest.raises(TaskControllerValidationError, match="writable target"):
        validate_execution_contracting(
            payload=_execute_payload(),
            scope=_scope(allowed_actions=["read_exact_source", "run_sandboxed_validation"]),
        )

    with pytest.raises(TaskControllerValidationError, match="real engineering work"):
        validate_execution_contracting(
            payload=_execute_payload(),
            scope=_scope(
                allowed_actions=["read_exact_source"],
                writable_targets=["taskcontroller"],
            ),
        )


def test_execute_requires_bounded_authority_evidence():
    with pytest.raises(TaskControllerValidationError, match="already-validated bounded execution authority"):
        validate_execution_contracting(
            payload=_execute_payload(execution_authority_active=False),
            scope=_scope(
                allowed_actions=["modify_approved_files"],
                writable_targets=["taskcontroller"],
            ),
        )

    with pytest.raises(TaskControllerValidationError, match="approval_digest"):
        validate_execution_contracting(
            payload=_execute_payload(approval_digest="sha256:bad"),
            scope=_scope(
                allowed_actions=["modify_approved_files"],
                writable_targets=["taskcontroller"],
            ),
        )


def test_execute_rejects_merge_deploy_or_production_authority_bundling():
    with pytest.raises(TaskControllerValidationError, match="separate merge/deploy/production authority"):
        validate_execution_contracting(
            payload=_execute_payload(),
            scope=_scope(
                allowed_actions=["modify_approved_files", "merge_approved_pr"],
                writable_targets=["taskcontroller"],
            ),
        )


def test_execute_rejects_routine_engineering_wait_points():
    with pytest.raises(TaskControllerValidationError, match="routine engineering conditions"):
        validate_execution_contracting(
            payload=_execute_payload(stop_conditions=["TEST_FAILURE", "SOURCE_OR_BASE_DRIFT"]),
            scope=_scope(
                allowed_actions=["modify_approved_files", "run_sandboxed_validation"],
                writable_targets=["taskcontroller"],
            ),
        )


def test_execute_accepts_end_to_end_real_work_package():
    receipt = validate_execution_contracting(
        payload=_execute_payload(),
        scope=_scope(
            allowed_actions=[
                "create_guarded_branch_or_worktree",
                "modify_approved_files",
                "run_sandboxed_validation",
                "stage",
                "create_commit",
                "push_working_branch",
                "open_or_update_draft_pr",
            ],
            writable_targets=["worktrees/gwc/SCRUM-781"],
        ),
    )

    assert receipt.mode == CONTRACT_MODE_EXECUTE
    assert receipt.real_work_required is True
    assert receipt.authority_granted is False
    assert "EXECUTION_CONTRACT_EXECUTE_OK" in receipt.reason_codes

def test_plan_requires_typed_hold_instead_of_ambiguous_hold_disposition():
    with pytest.raises(TaskControllerValidationError, match="AMBIGUOUS_HOLD_FORBIDDEN"):
        validate_execution_contracting(
            payload={
                "controller_contract_mode": CONTRACT_MODE_PLAN,
                "execution_authority_active": False,
                "disposition": "HOLD_CURRENT_USER_DENIAL",
            },
            scope=_scope(),
        )

    receipt = validate_execution_contracting(
        payload={
            "controller_contract_mode": CONTRACT_MODE_PLAN,
            "execution_authority_active": False,
            "disposition": "EFFECT_HOLD_ACTIVE",
            "hold": {
                "type": "EFFECT_HOLD",
                "denied_effects": ["git_write"],
                "control_loop_continues": True,
            },
        },
        scope=_scope(),
    )
    assert "HOLD:EFFECT_HOLD" in receipt.reason_codes


def test_run_hold_forbids_execute_dispatch():
    with pytest.raises(TaskControllerValidationError, match="RUN_HOLD forbids EXECUTE"):
        validate_execution_contracting(
            payload=_execute_payload(
                hold={
                    "type": "RUN_HOLD",
                    "denied_effects": [],
                    "control_loop_continues": False,
                }
            ),
            scope=_scope(
                allowed_actions=["modify_approved_files"],
                writable_targets=["taskcontroller"],
            ),
        )


def test_effect_hold_execute_scope_must_explicitly_deny_held_effects():
    payload = _execute_payload(
        hold={
            "type": "EFFECT_HOLD",
            "denied_effects": ["push_working_branch"],
            "control_loop_continues": True,
        }
    )
    with pytest.raises(TaskControllerValidationError, match="must also be denied by scope"):
        validate_execution_contracting(
            payload=payload,
            scope=_scope(
                allowed_actions=["modify_approved_files"],
                writable_targets=["taskcontroller"],
            ),
        )

    receipt = validate_execution_contracting(
        payload=payload,
        scope=_scope(
            allowed_actions=["modify_approved_files"],
            denied_actions=[
                "merge_approved_pr",
                "deploy_approved_release",
                "push_working_branch",
            ],
            writable_targets=["taskcontroller"],
        ),
    )
    assert receipt.mode == CONTRACT_MODE_EXECUTE

