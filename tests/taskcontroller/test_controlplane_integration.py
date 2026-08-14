"""WP5 S3 focused tests: projection-after-command integration (NO GWC)."""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.errors import StaleVersionError, TerminalRunError
from taskcontroller.controlplane.intents import ControlIntent
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


def _store(status=RunStatus.RUNNING.value, version=5):
    nodes = {
        "n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1", current_attempt=1, lease_ref="lease.1", artifact_refs=[]),
        "n2": NodeState(status=NodeStatus.DONE.value, contract_ref="ctr.2", current_attempt=1, lease_ref=None, artifact_refs=[]),
        "n3": NodeState(status=NodeStatus.PENDING.value, contract_ref="ctr.3", current_attempt=1, lease_ref=None, artifact_refs=[]),
    }
    state = TeamRunState(
        run_id="run.1", status=status, nodes=nodes,
        active_attempts=["att.1"], active_leases=["lease.1"], plan_version="plan.1",
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=state, version=version, meta=meta), -1)
    return store


class TestProjectionAfterCommand:
    def test_pause_state_and_projection_agree(self):
        cp = ControlPlane(_store())
        result, proj = cp.command(ControlIntent("PAUSE", "run.1", expected_version=5))
        assert result.status == RunStatus.PAUSED.value == proj.status
        assert proj.is_terminal is False
        # PAUSED run may RESUME or CANCEL
        assert "RESUME" in proj.legal_affordances
        assert "PAUSE" not in proj.legal_affordances

    def test_resume_state_and_projection_agree(self):
        cp = ControlPlane(_store(status=RunStatus.PAUSED.value))
        result, proj = cp.command(ControlIntent("RESUME", "run.1", expected_version=5))
        assert result.status == RunStatus.RUNNING.value == proj.status
        assert "PAUSE" in proj.legal_affordances

    def test_cancel_state_and_projection_agree(self):
        cp = ControlPlane(_store())
        result, proj = cp.command(ControlIntent("CANCEL", "run.1", expected_version=5))
        assert result.status == RunStatus.CANCELLED.value == proj.status
        assert proj.is_terminal is True
        assert proj.legal_affordances == ()
        # DONE node preserved in projection
        statuses = {n.node_id: n.status for n in proj.nodes}
        assert statuses["n2"] == NodeStatus.DONE.value

    def test_replan_state_and_projection_agree(self):
        cp = ControlPlane(_store())
        result, proj = cp.command(ControlIntent("REPLAN", "run.1", expected_version=5, new_plan_version="plan.2"))
        assert result.status == RunStatus.RUNNING.value == proj.status
        assert proj.plan_version == "plan.2"
        # DONE node n2 preserved across replan
        statuses = {n.node_id: n.status for n in proj.nodes}
        assert statuses["n2"] == NodeStatus.DONE.value


class TestIdempotencyAndConflict:
    def test_duplicate_command_id_idempotent(self):
        cp = ControlPlane(_store())
        r1, p1 = cp.command(ControlIntent("PAUSE", "run.1", expected_version=5, command_id="cmd.1"))
        r2, p2 = cp.command(ControlIntent("PAUSE", "run.1", expected_version=5, command_id="cmd.1"))
        assert r1 is r2
        assert p1.status == p2.status == RunStatus.PAUSED.value
        # only one version bump occurred
        assert cp._store.get_run("run.1").version == 6

    def test_conflicting_reuse_fails_closed(self):
        cp = ControlPlane(_store())
        # Pause succeeds; re-pause same expected_version (now stale) without command_id
        cp.command(ControlIntent("PAUSE", "run.1", expected_version=5, command_id="cmd.a"))
        with pytest.raises(StaleVersionError):
            cp.command(ControlIntent("RESUME", "run.1", expected_version=5))
