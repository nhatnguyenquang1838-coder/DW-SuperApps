"""WP1 DAG validation + readiness: validate_plan, compute_readiness, ALL_REQUIRED join.

Coverage:
- single-node plan (no deps)
- chain dependency (sequential)
- parallel dependencies
- ALL_REQUIRED join (every dep DONE -> READY)
- blocked on FAILED/CANCELLED dep
- blocked on absent (runtime unknown) dep
- cycle detection (Kahn)
- unknown dependency detection
- terminal nodes preserved
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import NodeStatus
from taskcontroller.domain.ids import TaskRef
from taskcontroller.domain.models import TaskContract
from taskcontroller.domain.values import CapabilityRequirement, NodeState, ScopeSpec
from taskcontroller.kernel.dag import compute_readiness, validate_plan
from taskcontroller.kernel.errors import (
    CycleDetectedError,
    UnknownDependencyError,
)


def _contract(
    contract_id: str,
    run_id: str = "run.1",
    node_id: str = "n1",
    deps: list[TaskRef] | None = None,
    plan_version: str = "p1",
    run_version: str = "r1",
    acceptance_criteria: list[str] | None = None,
    required_evidence: list = None,
) -> TaskContract:
    return TaskContract(
        contract_id=contract_id,
        run_id=run_id,
        node_id=node_id,
        objective=f"objective for {contract_id}",
        scope=ScopeSpec(allowed_work=["build"]),
        acceptance_criteria=acceptance_criteria or ["ok"],
        capability_requirement=CapabilityRequirement(capability_id="cap.build"),
        dependencies=deps or [],
        required_evidence=required_evidence or [],
        plan_version=plan_version,
        run_version=run_version,
    )


# ---------------------------------------------------------------------------
# validate_plan
# ---------------------------------------------------------------------------

def test_validate_plan_empty_noop():
    validate_plan([])


def test_validate_plan_single_node_no_deps():
    c = _contract("c.1", node_id="n1")
    validate_plan([c])


def test_validate_plan_chain_two_nodes():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    validate_plan([a, b])


def test_validate_plan_unknown_dependency_rejected():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="NOPE")])
    with pytest.raises(UnknownDependencyError):
        validate_plan([a, b])


def test_validate_plan_cycle_rejected():
    # n1 -> n2 -> n1
    a = _contract("c.1", node_id="n1", deps=[TaskRef(run_id="run.1", node_id="n2")])
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    with pytest.raises(CycleDetectedError):
        validate_plan([a, b])


def test_validate_plan_3node_chain():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    c = _contract("c.3", node_id="n3", deps=[TaskRef(run_id="run.1", node_id="n2")])
    validate_plan([a, b, c])


def test_validate_plan_self_dependency_rejected_by_wp0_model():
    # WP0 TaskContract.__post_init__ rejects self-dependency at construction time.
    # Here we just confirm validate_plan doesn't crash on a valid single-node plan.
    c = _contract("c.1", node_id="n1")
    validate_plan([c])


# ---------------------------------------------------------------------------
# compute_readiness
# ---------------------------------------------------------------------------

def test_readiness_single_node_no_dep_ready():
    c = _contract("c.1", node_id="n1")
    ns = NodeState(status=NodeStatus.PENDING.value, contract_ref="c.1")
    nodes = {"n1": ns}
    result = compute_readiness([c], nodes)
    assert result["n1"] == NodeStatus.READY.value


def test_readiness_node_with_pending_dep_stays_pending():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    nodes = {
        "n1": NodeState(status=NodeStatus.PENDING.value, contract_ref="c.1"),
        "n2": NodeState(status=NodeStatus.PENDING.value, contract_ref="c.2"),
    }
    result = compute_readiness([a, b], nodes)
    assert result["n1"] == NodeStatus.READY.value
    assert result["n2"] == NodeStatus.PENDING.value


def test_readiness_node_all_deps_done_ready():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    nodes = {
        "n1": NodeState(status=NodeStatus.DONE.value, contract_ref="c.1"),
        "n2": NodeState(status=NodeStatus.PENDING.value, contract_ref="c.2"),
    }
    result = compute_readiness([a, b], nodes)
    assert result["n1"] == NodeStatus.DONE.value
    assert result["n2"] == NodeStatus.READY.value


def test_readiness_node_blocked_on_failed_dep():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    nodes = {
        "n1": NodeState(status=NodeStatus.FAILED.value, contract_ref="c.1"),
        "n2": NodeState(status=NodeStatus.PENDING.value, contract_ref="c.2"),
    }
    result = compute_readiness([a, b], nodes)
    assert result["n2"] == NodeStatus.BLOCKED.value


def test_readiness_node_blocked_on_cancelled_dep():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    nodes = {
        "n1": NodeState(status=NodeStatus.CANCELLED.value, contract_ref="c.1"),
        "n2": NodeState(status=NodeStatus.PENDING.value, contract_ref="c.2"),
    }
    result = compute_readiness([a, b], nodes)
    assert result["n2"] == NodeStatus.BLOCKED.value


def test_readiness_node_blocked_when_dep_absent_at_runtime():
    a = _contract("c.1", node_id="n1")
    b = _contract("c.2", node_id="n2", deps=[TaskRef(run_id="run.1", node_id="n1")])
    nodes = {
        "n2": NodeState(status=NodeStatus.PENDING.value, contract_ref="c.2"),
        # n1 absent -> blocked
    }
    result = compute_readiness([a, b], nodes)
    assert result["n2"] == NodeStatus.BLOCKED.value


def test_readiness_parallel_deps_all_required():
    # n3 depends on both n1 and n2 (ALL_REQUIRED join)
    n3 = _contract("c.3", node_id="n3", deps=[
        TaskRef(run_id="run.1", node_id="n1"),
        TaskRef(run_id="run.1", node_id="n2"),
    ])
    nodes = {
        "n1": NodeState(status=NodeStatus.DONE.value),
        "n2": NodeState(status=NodeStatus.DONE.value),
        "n3": NodeState(status=NodeStatus.PENDING.value),
    }
    result = compute_readiness([n3], nodes)
    assert result["n3"] == NodeStatus.READY.value


def test_readiness_parallel_dep_one_not_done_stays_pending():
    n3 = _contract("c.3", node_id="n3", deps=[
        TaskRef(run_id="run.1", node_id="n1"),
        TaskRef(run_id="run.1", node_id="n2"),
    ])
    nodes = {
        "n1": NodeState(status=NodeStatus.DONE.value),
        "n2": NodeState(status=NodeStatus.RUNNING.value),
        "n3": NodeState(status=NodeStatus.PENDING.value),
    }
    result = compute_readiness([n3], nodes)
    assert result["n3"] == NodeStatus.PENDING.value


def test_readiness_terminal_node_preserved():
    c = _contract("c.1", node_id="n1")
    nodes = {"n1": NodeState(status=NodeStatus.DONE.value)}
    result = compute_readiness([c], nodes)
    assert result["n1"] == NodeStatus.DONE.value


def test_readiness_node_absent_in_state_map_leaves_entry_pending():
    c = _contract("c.1", node_id="n1")
    nodes = {}
    result = compute_readiness([c], nodes)
    assert result["n1"] == NodeStatus.PENDING.value
