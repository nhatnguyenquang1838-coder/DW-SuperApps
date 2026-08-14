"""WP5 S1 focused tests: deterministic projection model (NO GWC)."""

from __future__ import annotations

import copy

from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.domain.values import NodeState
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)


def _node(nid, status, attempt=1, lease=None, contract="ctr.1"):
    return NodeState(
        status=status, contract_ref=contract, current_attempt=attempt,
        lease_ref=lease, artifact_refs=[],
    )


def _vr(status=RunStatus.RUNNING.value, nodes=None, version=3, journal_position=7,
        plan_version="plan.1", active_leases=None, active_attempts=None):
    nodes = nodes or {
        "n1": _node("n1", NodeStatus.RUNNING.value),
        "n2": _node("n2", NodeStatus.REVIEWING.value),
        "n3": _node("n3", NodeStatus.BLOCKED.value),
    }
    state = TeamRunState(
        run_id="run.1", status=status, nodes=nodes,
        active_attempts=active_attempts or ["att.1"],
        active_leases=active_leases or ["lease.1"],
        plan_version=plan_version,
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=journal_position,
    )
    return VersionedRunState(state=state, version=version, meta=meta)


def _shuffled_nodes():
    # same content, different insertion order
    return {
        "n3": _node("n3", NodeStatus.BLOCKED.value),
        "n1": _node("n1", NodeStatus.RUNNING.value),
        "n2": _node("n2", NodeStatus.REVIEWING.value),
    }


class TestProjectionDeterminism:
    def test_same_input_byte_equivalent(self):
        p1 = RunProjection.from_versioned(_vr())
        p2 = RunProjection.from_versioned(_vr())
        assert p1.to_canonical_json() == p2.to_canonical_json()
        assert p1 == p2

    def test_node_insertion_order_does_not_alter_output(self):
        a = RunProjection.from_versioned(_vr(nodes=_shuffled_nodes()))
        b = RunProjection.from_versioned(_vr())
        assert a.to_canonical_json() == b.to_canonical_json()
        assert [n.node_id for n in a.nodes] == ["n1", "n2", "n3"]

    def test_deep_copy_input_not_mutated(self):
        vr = _vr()
        RunProjection.from_versioned(vr)
        # original VersionedRunState must be untouched by projection construction
        assert vr.state.status == RunStatus.RUNNING.value
        assert vr.version == 3


class TestProjectionContent:
    def test_counts_and_indicators(self):
        p = RunProjection.from_versioned(_vr())
        assert p.run_id == "run.1"
        assert p.status == RunStatus.RUNNING.value
        assert p.version == 3
        assert p.journal_position == 7
        assert p.plan_version == "plan.1"
        assert p.node_count == 3
        assert p.node_counts_by_status == {
            NodeStatus.RUNNING.value: 1,
            NodeStatus.REVIEWING.value: 1,
            NodeStatus.BLOCKED.value: 1,
        }
        assert p.has_blockers is True
        assert p.has_reviewing is True
        assert p.active_leases == ("lease.1",)
        assert p.is_terminal is False

    def test_runnning_affordances(self):
        p = RunProjection.from_versioned(_vr())
        # RUNNING may transition to PAUSED/BLOCKED/COMPLETED/FAILED/CANCELLED;
        # exposed intents: PAUSE, CANCEL, REPLAN (no RESUME from RUNNING)
        assert set(p.legal_affordances) == {"PAUSE", "CANCEL", "REPLAN"}
        assert "RESUME" not in p.legal_affordances


class TestProjectionTerminal:
    def test_terminal_run_exposes_no_illegal_affordances(self):
        for terminal in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value):
            p = RunProjection.from_versioned(_vr(status=terminal))
            assert p.is_terminal is True
            assert p.legal_affordances == ()

    def test_terminal_still_reports_counts(self):
        p = RunProjection.from_versioned(_vr(status=RunStatus.COMPLETED.value))
        assert p.node_count == 3
        assert p.has_reviewing is True
