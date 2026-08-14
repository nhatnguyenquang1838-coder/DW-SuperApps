"""WP1 control ops: pause, cancel, replan, can_release_new_work.

Covers:
- can_release_new_work: only RUNNING releases; all others don't
- pause: RUNNING -> PAUSED; invalid sources rejected
- cancel: non-terminal -> CANCELLED; preserves DONE nodes; terminal rejected
- replan: new plan_version, DONE preserved, non-terminal reset, terminal rejected,
  FAILED not re-RUNNING, version must change
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.values import NodeState
from taskcontroller.kernel.control import (
    can_release_new_work,
    cancel,
    pause,
    replan,
)
from taskcontroller.kernel.errors import ReplanPreconditionError, TransitionRejected
from taskcontroller.kernel.transitions import validate_run_transition


def _run_state(
    status: str = RunStatus.RUNNING.value,
    plan_version: str = "p1",
    run_version: str = "r1",
    nodes: dict[str, NodeState] | None = None,
):
    from taskcontroller.domain.models import TeamRunState

    return TeamRunState(
        run_id="run.1",
        status=status,
        nodes=nodes or {},
        plan_version=plan_version,
        run_version=run_version,
    )


def _node(nid: str, status: str, contract_ref: str = "", artifact_refs: list[str] | None = None):
    return NodeState(
        status=status,
        contract_ref=contract_ref,
        artifact_refs=artifact_refs or [],
    )


# ---------------------------------------------------------------------------
# can_release_new_work
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,expected",
    [
        (RunStatus.RUNNING.value, True),
        (RunStatus.CREATED.value, False),
        (RunStatus.PLANNED.value, False),
        (RunStatus.PAUSED.value, False),
        (RunStatus.BLOCKED.value, False),
        (RunStatus.COMPLETED.value, False),
        (RunStatus.FAILED.value, False),
        (RunStatus.CANCELLED.value, False),
    ],
)
def test_can_release_new_work_by_status(status, expected):
    run = _run_state(status=status)
    assert can_release_new_work(run) is expected


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------

def test_pause_running_to_paused():
    run = _run_state(status=RunStatus.RUNNING.value, nodes={"n1": _node("n1", NodeStatus.RUNNING.value)})
    result = pause(run)
    assert result.status == RunStatus.PAUSED.value
    assert result.nodes["n1"].status == NodeStatus.RUNNING.value  # DONE not involved here


def test_pause_from_paused_rejected():
    run = _run_state(status=RunStatus.PAUSED.value)
    with pytest.raises(TransitionRejected):
        pause(run)


def test_pause_from_created_rejected():
    run = _run_state(status=RunStatus.CREATED.value)
    with pytest.raises(TransitionRejected):
        pause(run)


def test_pause_preserves_node_states():
    run = _run_state(
        status=RunStatus.RUNNING.value,
        nodes={
            "n1": _node("n1", NodeStatus.RUNNING.value),
            "n2": _node("n2", NodeStatus.PENDING.value),
        },
    )
    result = pause(run)
    assert result.nodes["n1"].status == NodeStatus.RUNNING.value
    assert result.nodes["n2"].status == NodeStatus.PENDING.value


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------

def test_cancel_running_to_cancelled():
    run = _run_state(status=RunStatus.RUNNING.value, nodes={"n1": _node("n1", NodeStatus.RUNNING.value)})
    result = cancel(run)
    assert result.status == RunStatus.CANCELLED.value


def test_cancel_non_terminal_accepted():
    for status in (RunStatus.CREATED.value, RunStatus.PLANNED.value, RunStatus.PAUSED.value, RunStatus.BLOCKED.value):
        run = _run_state(status=status)
        result = cancel(run)
        assert result.status == RunStatus.CANCELLED.value


def test_cancel_terminal_rejected():
    for status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value):
        run = _run_state(status=status)
        with pytest.raises(TransitionRejected):
            cancel(run)


def test_cancel_preserves_done_nodes():
    run = _run_state(
        status=RunStatus.RUNNING.value,
        nodes={
            "n1": _node("n1", NodeStatus.DONE.value, contract_ref="c.1"),
            "n2": _node("n2", NodeStatus.RUNNING.value),
        },
    )
    result = cancel(run)
    assert result.status == RunStatus.CANCELLED.value
    assert result.nodes["n1"].status == NodeStatus.DONE.value  # DONE preserved
    assert result.nodes["n2"].status == NodeStatus.CANCELLED.value  # non-terminal forced to CANCELLED


def test_cancel_force_non_terminal_nodes_cancelled():
    run = _run_state(
        status=RunStatus.RUNNING.value,
        nodes={
            "n1": _node("n1", NodeStatus.PENDING.value),
            "n2": _node("n2", NodeStatus.RUNNING.value),
        },
    )
    result = cancel(run)
    # non-terminal nodes are re-initialized to CANCELLED in control.py cancel()
    for nid, ns in result.nodes.items():
        assert ns.status == NodeStatus.CANCELLED.value, f"node {nid} not CANCELLED"


# ---------------------------------------------------------------------------
# replan
# ---------------------------------------------------------------------------

def test_replan_new_plan_version_run_returns_running():
    run = _run_state(status=RunStatus.RUNNING.value, plan_version="p1", nodes={"n1": _node("n1", NodeStatus.PENDING.value)})
    result = replan(run, contracts=[], new_plan_version="p2")
    assert result.status == RunStatus.RUNNING.value
    assert result.plan_version == "p2"
    assert result.run_version == "r1"  # unchanged


def test_replan_non_terminal_preconditions():
    for status in (RunStatus.CREATED.value, RunStatus.PLANNED.value, RunStatus.PAUSED.value, RunStatus.BLOCKED.value):
        run = _run_state(status=status, plan_version="p1")
        result = replan(run, contracts=[], new_plan_version="p2")
        assert result.status == RunStatus.RUNNING.value
        assert result.plan_version == "p2"


def test_replan_same_plan_version_rejected():
    run = _run_state(status=RunStatus.RUNNING.value, plan_version="p1")
    with pytest.raises(Exception):  # KernelError
        replan(run, contracts=[], new_plan_version="p1")


def test_replan_failed_rejected():
    run = _run_state(status=RunStatus.FAILED.value, plan_version="p1")
    with pytest.raises(ReplanPreconditionError):
        replan(run, contracts=[], new_plan_version="p2")


def test_replan_completed_rejected():
    run = _run_state(status=RunStatus.COMPLETED.value, plan_version="p1")
    with pytest.raises(ReplanPreconditionError):
        replan(run, contracts=[], new_plan_version="p2")


def test_replan_cancelled_rejected():
    run = _run_state(status=RunStatus.CANCELLED.value, plan_version="p1")
    with pytest.raises(ReplanPreconditionError):
        replan(run, contracts=[], new_plan_version="p2")


def test_replan_preserves_done_nodes():
    run = _run_state(
        status=RunStatus.RUNNING.value,
        plan_version="p1",
        nodes={
            "n1": _node("n1", NodeStatus.DONE.value, contract_ref="c.1", artifact_refs=["a.1"]),
            "n2": _node("n2", NodeStatus.PENDING.value, contract_ref="c.2"),
        },
    )
    result = replan(run, contracts=[], new_plan_version="p2")
    assert result.status == RunStatus.RUNNING.value
    assert result.plan_version == "p2"
    assert result.nodes["n1"].status == NodeStatus.DONE.value
    assert result.nodes["n1"].contract_ref == "c.1"
    assert result.nodes["n1"].artifact_refs == ["a.1"]
    # non-terminal reset to PENDING
    assert result.nodes["n2"].status == NodeStatus.PENDING.value


def test_replan_preserves_multiple_done_nodes():
    run = _run_state(
        status=RunStatus.RUNNING.value,
        plan_version="p1",
        nodes={
            "n1": _node("n1", NodeStatus.DONE.value, contract_ref="c.1", artifact_refs=["a.1"]),
            "n2": _node("n2", NodeStatus.DONE.value, contract_ref="c.2", artifact_refs=["a.2"]),
            "n3": _node("n3", NodeStatus.FAILED.value),
        },
    )
    result = replan(run, contracts=[], new_plan_version="p2")
    assert result.status == RunStatus.RUNNING.value
    assert result.plan_version == "p2"
    for nid in ("n1", "n2"):
        assert result.nodes[nid].status == NodeStatus.DONE.value
        assert result.nodes[nid].artifact_refs  # preserved
    # FAILED node also preserved (it's non-terminal-but-spec says preserve DONE; non-terminal others reset)
    assert result.nodes["n3"].status == NodeStatus.PENDING.value


def test_replan_new_run_version():
    run = _run_state(status=RunStatus.RUNNING.value, plan_version="p1", run_version="r1")
    result = replan(run, contracts=[], new_plan_version="p2", new_run_version="r2")
    assert result.run_version == "r2"


def test_replan_keeps_run_version_if_not_given():
    run = _run_state(status=RunStatus.RUNNING.value, plan_version="p1", run_version="r1")
    result = replan(run, contracts=[], new_plan_version="p2")
    assert result.run_version == "r1"


def test_replan_version_mismatch_object():
    # contracts param is a list; replan checks new_plan_version != current
    run = _run_state(status=RunStatus.RUNNING.value, plan_version="p1")
    with pytest.raises(Exception):
        replan(run, contracts=[], new_plan_version="p1")


# ---------------------------------------------------------------------------
# replan with contracts (DAG preserved on replan)
# ---------------------------------------------------------------------------

def test_replan_preserves_done_nodes_with_contracts_param():
    from taskcontroller.domain.models import TaskContract
    from taskcontroller.domain.values import CapabilityRequirement, ScopeSpec

    c1 = TaskContract(
        contract_id="c.1",
        run_id="run.1",
        node_id="n1",
        objective="x",
        scope=ScopeSpec(allowed_work=["build"]),
        acceptance_criteria=["ok"],
        capability_requirement=CapabilityRequirement(capability_id="cap.build"),
        plan_version="p1",
        run_version="r1",
    )
    run = _run_state(
        status=RunStatus.RUNNING.value,
        plan_version="p1",
        nodes={"n1": _node("n1", NodeStatus.DONE.value, contract_ref="c.1", artifact_refs=["a.1"])},
    )
    result = replan(run, contracts=[c1], new_plan_version="p2")
    assert result.plan_version == "p2"
    assert result.nodes["n1"].status == NodeStatus.DONE.value
    assert result.nodes["n1"].artifact_refs == ["a.1"]
