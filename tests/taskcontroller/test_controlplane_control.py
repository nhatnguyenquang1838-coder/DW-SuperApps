"""WP5 S2 focused tests: control intents + authority boundary (NO GWC)."""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.engine import ControlEngine
from taskcontroller.controlplane.errors import (
    ControlPlaneError,
    StaleVersionError,
    TerminalRunError,
)
from taskcontroller.controlplane.intents import ControlIntent, ControlResult
from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.kernel.errors import ReplanPreconditionError
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


def _node(nid, status, attempt=1, lease=None):
    return NodeState(
        status=status, contract_ref="ctr.1", current_attempt=attempt,
        lease_ref=lease, artifact_refs=[],
    )


def _make_store(status=RunStatus.RUNNING.value, nodes=None, version=5):
    nodes = nodes or {
        "n1": _node("n1", NodeStatus.RUNNING.value),
        # a historical DONE node that must survive cancel/replan
        "n2": _node("n2", NodeStatus.DONE.value),
        "n3": _node("n3", NodeStatus.PENDING.value),
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


class TestPauseResume:
    def test_running_pause_then_resume(self):
        store = _make_store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        r = eng.apply(ControlIntent("PAUSE", "run.1", expected_version=5))
        assert r.accepted and r.status == RunStatus.PAUSED.value
        # resume only legal from PAUSED
        r2 = eng.apply(ControlIntent("RESUME", "run.1", expected_version=r.new_version))
        assert r2.accepted and r2.status == RunStatus.RUNNING.value

    def test_resume_from_running_rejected(self):
        store = _make_store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        # RUNNING -> RUNNING is not a legal transition
        with pytest.raises(TerminalRunError):
            eng.apply(ControlIntent("RESUME", "run.1", expected_version=5))

    def test_resume_from_blocked_ok(self):
        store = _make_store(status=RunStatus.BLOCKED.value)
        eng = ControlEngine(store)
        r = eng.apply(ControlIntent("RESUME", "run.1", expected_version=5))
        assert r.status == RunStatus.RUNNING.value


class TestCancel:
    def test_cancel_non_terminal(self):
        store = _make_store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        r = eng.apply(ControlIntent("CANCEL", "run.1", expected_version=5))
        assert r.accepted and r.status == RunStatus.CANCELLED.value
        # DONE node n2 preserved; non-terminal n1/n3 forced CANCELLED
        st = store.get_run("run.1").state
        assert st.nodes["n2"].status == NodeStatus.DONE.value
        assert st.nodes["n1"].status == NodeStatus.CANCELLED.value

    def test_cancel_terminal_fails_closed(self):
        for terminal in (RunStatus.COMPLETED.value, RunStatus.CANCELLED.value, RunStatus.FAILED.value):
            store = _make_store(status=terminal)
            eng = ControlEngine(store)
            with pytest.raises(TerminalRunError):
                eng.apply(ControlIntent("CANCEL", "run.1", expected_version=5))


class TestReplan:
    def test_replan_requires_new_plan_version(self):
        store = _make_store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        r = eng.apply(ControlIntent("REPLAN", "run.1", expected_version=5, new_plan_version="plan.2"))
        assert r.accepted and r.status == RunStatus.RUNNING.value
        assert store.get_run("run.1").state.plan_version == "plan.2"
        # DONE node n2 preserved verbatim
        assert store.get_run("run.1").state.nodes["n2"].status == NodeStatus.DONE.value

    def test_replan_same_plan_version_rejected(self):
        store = _make_store(status=RunStatus.RUNNING.value, version=5)
        eng = ControlEngine(store)
        with pytest.raises(ControlPlaneError):
            eng.apply(ControlIntent("REPLAN", "run.1", expected_version=5, new_plan_version="plan.1"))

    def test_replan_on_terminal_rejected(self):
        store = _make_store(status=RunStatus.COMPLETED.value)
        eng = ControlEngine(store)
        with pytest.raises((TerminalRunError, ControlPlaneError, ReplanPreconditionError)):
            eng.apply(ControlIntent("REPLAN", "run.1", expected_version=5, new_plan_version="plan.2"))


class TestStaleCAS:
    def test_stale_expected_version_no_partial_mutation(self):
        store = _make_store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        # bump live version out from under the intent
        live = store.get_run("run.1")
        store.put_run(VersionedRunState(state=live.state, version=live.version + 1, meta=live.meta), live.version)
        with pytest.raises(StaleVersionError):
            eng.apply(ControlIntent("PAUSE", "run.1", expected_version=5))
        # state untouched: still RUNNING at version 6
        cur = store.get_run("run.1")
        assert cur.state.status == RunStatus.RUNNING.value
        assert cur.version == 6

    def test_idempotent_command_no_second_apply(self):
        store = _make_store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        r1 = eng.apply(ControlIntent("PAUSE", "run.1", expected_version=5, command_id="cmd.pause.1"))
        assert r1.new_version == 6
        # re-apply with stale expected_version but same command_id => prior result
        r2 = eng.apply(ControlIntent("PAUSE", "run.1", expected_version=5, command_id="cmd.pause.1"))
        assert r2 is r1
        # live version must NOT have advanced again
        assert store.get_run("run.1").version == 6


class TestUnknownIntent:
    def test_unknown_intent_typed_reject(self):
        from taskcontroller.controlplane.errors import UnknownIntentError

        with pytest.raises(UnknownIntentError):
            ControlIntent("EXPLODE", "run.1", expected_version=5)
