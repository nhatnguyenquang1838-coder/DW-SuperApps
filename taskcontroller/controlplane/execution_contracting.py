"""Controller execution-contract guard for real bounded engineering work.

This guard separates planning/repair semantics from approved implementation.
It does not grant authority. It validates that once a Controller declares an
EXECUTE contract, the contract actually contains bounded writable engineering
work instead of another read/validate/report-only loop.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping, NoReturn, Sequence

from taskcontroller.errors import TaskControllerValidationError

CONTRACT_MODE_PLAN = "PLAN"
CONTRACT_MODE_EXECUTE = "EXECUTE"
CONTRACT_MODE_TRANSPORT_REPAIR = "TRANSPORT_REPAIR"
_SUPPORTED_MODES = frozenset({CONTRACT_MODE_PLAN, CONTRACT_MODE_EXECUTE, CONTRACT_MODE_TRANSPORT_REPAIR})

_REAL_WORK_ACTIONS = frozenset({
    "create_guarded_branch_or_worktree",
    "modify_approved_files",
    "run_sandboxed_validation",
    "stage",
    "create_commit",
    "push_working_branch",
    "open_or_update_draft_pr",
})

_SEPARATE_AUTHORITY_ACTIONS = frozenset({
    "mark_pr_ready_for_review",
    "merge_approved_pr",
    "deploy_approved_release",
    "production_config_change",
    "production_data_write",
    "migration",
    "credential_rotation",
    "branch_deletion",
    "force_push",
})

_ROUTINE_ENGINEERING_STOP_CONDITIONS = frozenset({
    "RED_COMPLETE",
    "GREEN_COMPLETE",
    "TEST_FAILURE",
    "LINT_FAILURE",
    "REFACTOR_NEEDED",
    "ROUTINE_IMPLEMENTATION_DECISION",
})

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

class ExecutionContractingError(TaskControllerValidationError):
    """Stable fail-closed error for invalid Controller execution contracting."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ExecutionContractingReceipt:
    mode: str
    reason_codes: tuple[str, ...]
    real_work_required: bool
    authority_granted: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "reason_codes": list(self.reason_codes),
            "real_work_required": self.real_work_required,
            "authority_granted": self.authority_granted,
        }


def _fail(code: str, message: str) -> NoReturn:
    raise ExecutionContractingError(code, message)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        _fail("EXECUTION_CONTRACT_INVALID", f"{field} must be an object")
    return copy.deepcopy(dict(value))


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("EXECUTION_CONTRACT_INVALID", f"{field} must be non-empty")
    return value.strip()


def _string_list(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("EXECUTION_CONTRACT_INVALID", f"{field} must be an array")
    normalized = tuple(_text(item, f"{field}[]") for item in value)
    if not allow_empty and not normalized:
        _fail("EXECUTION_CONTRACT_INVALID", f"{field} must not be empty")
    if len(set(normalized)) != len(normalized):
        _fail("EXECUTION_CONTRACT_INVALID", f"{field} must not contain duplicates")
    return normalized


def _work_packages(value: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence) or not value:
        _fail("EXECUTION_CONTRACT_WORK_PACKAGES_REQUIRED", "EXECUTE requires work_packages")
    packages: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(value):
        package = _mapping(item, f"work_packages[{index}]")
        package_id = _text(package.get("id"), f"work_packages[{index}].id")
        _text(package.get("objective"), f"work_packages[{index}].objective")
        if package_id in ids:
            _fail("EXECUTION_CONTRACT_INVALID", f"duplicate work package id {package_id!r}")
        ids.add(package_id)
        packages.append(package)
    return tuple(packages)


def validate_execution_contracting(*, payload: Mapping[str, Any], scope: Mapping[str, Any] | Any) -> ExecutionContractingReceipt:
    """Validate PLAN/EXECUTE/TRANSPORT_REPAIR semantics without granting authority.

    Requests that predate this contract and omit controller_contract_mode remain
    valid in COMPATIBILITY mode. Canonical Controller instructions require new
    requests to declare a mode explicitly.
    """

    request_payload = _mapping(payload, "payload")
    mode = request_payload.get("controller_contract_mode")
    if mode is None:
        return ExecutionContractingReceipt(
            mode="COMPATIBILITY",
            reason_codes=("EXECUTION_CONTRACT_COMPATIBILITY",),
            real_work_required=False,
        )

    mode = _text(mode, "controller_contract_mode").upper()
    if mode not in _SUPPORTED_MODES:
        _fail("EXECUTION_CONTRACT_MODE_UNSUPPORTED", f"unsupported mode {mode!r}")

    normalized_scope = _mapping(scope, "scope")
    allowed = set(_string_list(normalized_scope.get("allowed_actions", ()), "scope.allowed_actions", allow_empty=True))
    writable = set(_string_list(normalized_scope.get("writable_targets", ()), "scope.writable_targets", allow_empty=True))

    authority_active = request_payload.get("execution_authority_active", False)
    if not isinstance(authority_active, bool):
        _fail("EXECUTION_CONTRACT_INVALID", "execution_authority_active must be boolean when present")

    if mode in {CONTRACT_MODE_PLAN, CONTRACT_MODE_TRANSPORT_REPAIR}:
        if authority_active:
            _fail("EXECUTION_CONTRACT_AUTHORITY_FORBIDDEN", f"{mode} must not claim active execution authority")
        if allowed.intersection(_REAL_WORK_ACTIONS):
            _fail("EXECUTION_CONTRACT_READONLY_MODE_MUTATION", f"{mode} cannot include real-work mutation actions")
        return ExecutionContractingReceipt(
            mode=mode,
            reason_codes=(f"EXECUTION_CONTRACT_{mode}_OK",),
            real_work_required=False,
        )

    if not authority_active:
        _fail("EXECUTION_CONTRACT_AUTHORITY_REQUIRED", "EXECUTE requires already-validated bounded execution authority")
    execution_plan_ref = _text(request_payload.get("execution_plan_ref"), "execution_plan_ref")
    approval_ref = _text(request_payload.get("approval_ref"), "approval_ref")
    approval_digest = _text(request_payload.get("approval_digest"), "approval_digest")
    if _DIGEST_RE.fullmatch(approval_digest) is None:
        _fail("EXECUTION_CONTRACT_APPROVAL_DIGEST_INVALID", "approval_digest must be sha256:<64 lowercase hex>")
    if not writable:
        _fail("EXECUTION_CONTRACT_WRITABLE_SCOPE_REQUIRED", "EXECUTE requires at least one writable target")

    real_actions = allowed.intersection(_REAL_WORK_ACTIONS)
    if not real_actions:
        _fail("EXECUTION_CONTRACT_REAL_WORK_REQUIRED", "EXECUTE must authorize at least one real engineering work action")

    separate_effects = allowed.intersection(_SEPARATE_AUTHORITY_ACTIONS)
    if separate_effects:
        _fail(
            "EXECUTION_CONTRACT_EFFECT_AUTHORITY_SEPARATE",
            "EXECUTE cannot bundle separate merge/deploy/production authority: " + ", ".join(sorted(separate_effects)),
        )

    packages = _work_packages(request_payload.get("work_packages"))
    continue_until = _string_list(request_payload.get("continue_until"), "continue_until")
    stop_conditions = _string_list(request_payload.get("stop_conditions"), "stop_conditions")
    routine_stops = _ROUTINE_ENGINEERING_STOP_CONDITIONS.intersection(stop_conditions)
    if routine_stops:
        _fail(
            "EXECUTION_CONTRACT_ROUTINE_WAIT_FORBIDDEN",
            "routine engineering conditions cannot be hard stop conditions: " + ", ".join(sorted(routine_stops)),
        )

    return ExecutionContractingReceipt(
        mode=mode,
        reason_codes=(
            "EXECUTION_CONTRACT_EXECUTE_OK",
            f"EXECUTION_PLAN_REF:{execution_plan_ref}",
            f"APPROVAL_REF:{approval_ref}",
            f"WORK_PACKAGES:{len(packages)}",
            f"REAL_ACTIONS:{len(real_actions)}",
            f"CONTINUE_UNTIL:{len(continue_until)}",
            f"STOP_CONDITIONS:{len(stop_conditions)}",
        ),
        real_work_required=True,
    )


__all__ = [
    "CONTRACT_MODE_EXECUTE",
    "CONTRACT_MODE_PLAN",
    "CONTRACT_MODE_TRANSPORT_REPAIR",
    "ExecutionContractingError",
    "ExecutionContractingReceipt",
    "validate_execution_contracting",
]
