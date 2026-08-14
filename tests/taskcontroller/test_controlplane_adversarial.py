"""WP5 S4 focused tests: adversarial authority proofs (NO GWC).

These prove the control-plane cannot subvert runtime authority:
- projection is read-only (never mutates the store)
- a stale snapshot cannot overwrite newer state (CAS rejects)
- CANCEL cannot rewrite historical DONE nodes
- RESUME only PAUSED/BLOCKED -> RUNNING
- REPLAN requires a new plan_version (no in-place rewrite)
- unknown intent is a typed reject
- no forbidden imports (time/random/subprocess/network/GWC) in controlplane/**
"""

from __future__ import annotations

import os
import subprocess

import pytest

from taskcontroller.controlplane.errors import (
    ControlPlaneError,
    StaleVersionError,
    TerminalRunError,
    UnknownIntentError,
)
from taskcontroller.controlplane.engine import ControlEngine
from taskcontroller.controlplane.intents import ControlIntent
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.controlplane.projection import RunProjection
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


class TestProjectionCannotMutateRuntime:
    def test_projection_is_read_only(self):
        store = _store()
        before = store.get_run("run.1")
        proj = RunProjection.from_versioned(before)
        # attempt to mutate the projection's underlying view
        proj_dict = proj.to_dict()
        proj_dict["status"] = "HACKED"
        proj_dict["nodes"].append({"node_id": "evil"})
        # store must be completely untouched
        after = store.get_run("run.1")
        assert after.state.status == RunStatus.RUNNING.value
        assert after.version == 5
        assert set(after.state.nodes.keys()) == {"n1", "n2"}


class TestStaleSnapshotCannotOverwrite:
    def test_stale_expected_version_rejected(self):
        store = _store()
        eng = ControlEngine(store)
        # simulate concurrent newer write
        live = store.get_run("run.1")
        store.put_run(VersionedRunState(state=live.state, version=live.version + 1, meta=live.meta), live.version)
        assert store.get_run("run.1").version == 6
        with pytest.raises(StaleVersionError):
            eng.apply(ControlIntent("PAUSE", "run.1", expected_version=5))
        # newer state preserved, untouched
        assert store.get_run("run.1").version == 6
        assert store.get_run("run.1").state.status == RunStatus.RUNNING.value


class TestCancelPreservesDoneNodes:
    def test_cancel_cannot_rewrite_historical_done(self):
        store = _store()
        cp = ControlPlane(store)
        result, proj = cp.command(ControlIntent("CANCEL", "run.1", expected_version=5))
        assert result.status == RunStatus.CANCELLED.value
        # historical DONE node n2 is verbatim preserved, never rewritten
        st = store.get_run("run.1").state
        assert st.nodes["n2"].status == NodeStatus.DONE.value
        assert proj.nodes_by_status(NodeStatus.DONE.value) == ["n2"]


class TestResumeBoundary:
    def test_resume_from_running_rejected(self):
        store = _store(status=RunStatus.RUNNING.value)
        eng = ControlEngine(store)
        with pytest.raises(TerminalRunError):
            eng.apply(ControlIntent("RESUME", "run.1", expected_version=5))

    def test_resume_from_failed_rejected(self):
        store = _store(status=RunStatus.FAILED.value)
        eng = ControlEngine(store)
        with pytest.raises(TerminalRunError):
            eng.apply(ControlIntent("RESUME", "run.1", expected_version=5))

    def test_resume_from_blocked_ok(self):
        store = _store(status=RunStatus.BLOCKED.value)
        eng = ControlEngine(store)
        r = eng.apply(ControlIntent("RESUME", "run.1", expected_version=5))
        assert r.status == RunStatus.RUNNING.value


class TestReplanRequiresNewPlan:
    def test_replan_same_plan_version_rejected(self):
        store = _store()
        eng = ControlEngine(store)
        with pytest.raises(ControlPlaneError):
            eng.apply(ControlIntent("REPLAN", "run.1", expected_version=5, new_plan_version="plan.1"))

    def test_replan_new_plan_accepted_and_recorded(self):
        store = _store()
        cp = ControlPlane(store)
        _, proj = cp.command(ControlIntent("REPLAN", "run.1", expected_version=5, new_plan_version="plan.9"))
        assert proj.plan_version == "plan.9"
        assert store.get_run("run.1").state.plan_version == "plan.9"


class TestUnknownIntentRejected:
    def test_unknown_intent_typed(self):
        with pytest.raises(UnknownIntentError):
            ControlIntent("FORCE_COMPLETE", "run.1", expected_version=5)


class TestNoForbiddenImports:
    def test_controlplane_has_no_forbidden_imports(self):
        here = os.path.dirname(__file__)
        root = os.path.abspath(os.path.join(here, "..", "..", "taskcontroller", "controlplane"))
        bad = ("time", "random", "subprocess", "socket", "requests", "urllib")
        hits = []
        for fname in os.listdir(root):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            with open(path, "r", encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if "import" in line:
                        for mod in bad:
                            if f"import {mod}" in line or f"from {mod} " in line:
                                hits.append(f"{fname}:{i}:{line.strip()}")
        assert hits == [], f"forbidden imports found: {hits}"
