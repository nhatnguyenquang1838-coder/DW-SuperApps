"""TC-MBX-306: executable ExecutionBoundary and child-subset proof."""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.execution_boundary import (
    ExecutionBoundary,
    ExecutionBoundaryValidationError,
    REPLAN_REQUIRED,
    prove_child_subset,
)


_REPLAN_TRIGGERS = (
    "action_not_allowed",
    "authority_expansion",
    "new_source_required",
    "scope_expansion",
)


def _boundary(**changes: object) -> ExecutionBoundary:
    values: dict[str, object] = {
        "allowed_actions": ("analyze", "execute_tests", "read_repo", "review"),
        "denied_actions": ("deploy", "merge", "mutate_production"),
        "writable_targets": ("taskcontroller",),
        "source_roots": ("taskcontroller", "tests/taskcontroller"),
        "max_children": 6,
        "max_parallel": 4,
        "max_depth": 2,
        "replan_required_when": _REPLAN_TRIGGERS,
    }
    values.update(changes)
    return ExecutionBoundary(**values)


def test_boundary_is_canonical_and_digest_covers_all_capability_fields() -> None:
    first = _boundary(
        allowed_actions=("review", "read_repo", "analyze", "execute_tests"),
        denied_actions=("mutate_production", "merge", "deploy"),
        writable_targets=("taskcontroller",),
        source_roots=("tests/taskcontroller", "taskcontroller"),
        replan_required_when=("scope_expansion", "new_source_required", "authority_expansion", "action_not_allowed"),
    )
    second = _boundary()

    assert first.to_dict() == second.to_dict()
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.digest() == first.scope_digest
    assert first.to_dict()["scope_digest"].startswith("sha256:")
    assert ExecutionBoundary.from_dict(first.to_dict()).to_dict() == first.to_dict()

    for field, changed in (
        ("allowed_actions", ("analyze", "execute_tests", "read_repo")),
        ("denied_actions", ("deploy", "merge")),
        ("writable_targets", ("taskcontroller/subsystem",)),
        ("source_roots", ("taskcontroller/subsystem",)),
        ("max_children", 5),
        ("max_parallel", 3),
        ("max_depth", 1),
        ("replan_required_when", ("scope_expansion",)),
    ):
        changed_payload = first.to_dict()
        changed_payload[field] = changed
        changed_payload.pop("scope_digest")
        assert ExecutionBoundary.from_dict(changed_payload).digest() != first.digest()


def test_boundary_rejects_conflicting_or_unsafe_values() -> None:
    with pytest.raises(ExecutionBoundaryValidationError, match="overlap"):
        _boundary(allowed_actions=("read_repo",), denied_actions=("read_repo",))

    with pytest.raises(ExecutionBoundaryValidationError, match="source_roots"):
        _boundary(source_roots=())

    with pytest.raises(ExecutionBoundaryValidationError, match="max_parallel"):
        _boundary(max_parallel=0)

    with pytest.raises(ExecutionBoundaryValidationError, match="max_depth"):
        _boundary(max_depth=9)

    with pytest.raises(ExecutionBoundaryValidationError, match="replan_required_when"):
        _boundary(replan_required_when=())


def test_child_boundary_produces_mechanical_subset_proof() -> None:
    parent = _boundary()
    child = _boundary(
        allowed_actions=("analyze", "read_repo"),
        denied_actions=("deploy", "merge", "mutate_production", "write_unrelated"),
        writable_targets=("taskcontroller/controlplane",),
        source_roots=("taskcontroller/controlplane",),
        max_children=2,
        max_parallel=1,
        max_depth=1,
        replan_required_when=_REPLAN_TRIGGERS + ("output_contract_missing",),
    )

    proof = prove_child_subset(parent, child)

    assert proof.valid is True
    assert proof.parent_scope_digest == parent.scope_digest
    assert proof.child_scope_digest == child.scope_digest
    assert proof.checks == (
        "allowed_actions_subset",
        "denied_actions_preserved",
        "writable_targets_subset",
        "source_roots_subset",
        "child_budgets_within_parent",
        "replan_triggers_preserved",
    )
    assert parent.validate_child_subset(child) == proof
    assert proof.to_dict()["valid"] is True


def test_child_action_expansion_is_replan_required() -> None:
    parent = _boundary()
    child = _boundary(allowed_actions=("analyze", "read_repo", "write_repo"))

    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        parent.validate_child_subset(child)

    assert caught.value.code == REPLAN_REQUIRED
    assert "allowed_actions_subset" in caught.value.failed_checks


def test_child_target_and_source_expansion_is_replan_required() -> None:
    parent = _boundary()

    for field, value, check in (
        ("writable_targets", ("taskcontroller", "outside"), "writable_targets_subset"),
        ("source_roots", ("taskcontroller", "outside"), "source_roots_subset"),
    ):
        with pytest.raises(ExecutionBoundaryValidationError) as caught:
            parent.validate_child_subset(_boundary(**{field: value}))
        assert caught.value.code == REPLAN_REQUIRED
        assert check in caught.value.failed_checks


def test_child_budget_depth_and_replan_trigger_expansion_are_rejected() -> None:
    parent = _boundary(max_depth=1)

    for field, value, check in (
        ("max_children", 7, "child_budgets_within_parent"),
        ("max_parallel", 5, "child_budgets_within_parent"),
        ("max_depth", 2, "child_budgets_within_parent"),
        ("replan_required_when", ("action_not_allowed", "scope_expansion"), "replan_triggers_preserved"),
    ):
        with pytest.raises(ExecutionBoundaryValidationError) as caught:
            parent.validate_child_subset(_boundary(**{field: value}))
        assert caught.value.code == REPLAN_REQUIRED
        assert check in caught.value.failed_checks

    nested_child = _boundary(max_depth=1)
    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        parent.validate_child_subset(nested_child, child_depth=1)
    assert caught.value.code == REPLAN_REQUIRED
    assert "child_budgets_within_parent" in caught.value.failed_checks


def test_path_prefix_must_be_segment_safe_and_malformed_child_fails_closed() -> None:
    parent = _boundary(writable_targets=("taskcontroller",), source_roots=("taskcontroller",))

    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        parent.validate_child_subset(
            _boundary(writable_targets=("taskcontroller-extra",), source_roots=("taskcontroller",))
        )
    assert caught.value.code == REPLAN_REQUIRED
    assert "writable_targets_subset" in caught.value.failed_checks

    wildcard_parent = _boundary(writable_targets=("taskcontroller/*",))
    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        wildcard_parent.validate_child_subset(
            _boundary(writable_targets=("taskcontroller/controlplane/*",))
        )
    assert caught.value.code == REPLAN_REQUIRED
    assert "writable_targets_subset" in caught.value.failed_checks

    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        prove_child_subset(parent, {"allowed_actions": ["read_repo"]})  # type: ignore[arg-type]
    assert caught.value.code == "SCHEMA_INVALID"


def test_supplied_digest_must_match_canonical_boundary_and_input_is_not_mutated() -> None:
    raw = _boundary().to_dict()
    before = dict(raw)
    raw["allowed_actions"] = ["read_repo"]
    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        ExecutionBoundary.from_dict(raw)
    assert caught.value.code == "DIGEST_MISMATCH"

    assert before["allowed_actions"] == ["analyze", "execute_tests", "read_repo", "review"]


def test_boundary_module_has_no_provider_or_transport_execution_path() -> None:
    from pathlib import Path

    from taskcontroller.controlplane import execution_boundary

    source = Path(execution_boundary.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "import requests" not in source
    assert "hermes-cloud" not in source
    assert "provider_id" not in source
    assert "socket" not in source
