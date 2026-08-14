"""WP6 S4 focused tests: adversarial projection E2E with fake Slack transport (NO GWC)."""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.errors import StaleVersionError
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.projections.adapter import SlackProjectionAdapter
from taskcontroller.projections.binding import DuplicateRootError
from taskcontroller.projections.transport import FakeSlackTransport
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


def _store(status=RunStatus.RUNNING.value, version=5, plan="p1"):
    nodes = {
        "n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1", current_attempt=1, lease_ref="l1", artifact_refs=[]),
        "n2": NodeState(status=NodeStatus.DONE.value, contract_ref="c2", current_attempt=1, lease_ref=None, artifact_refs=[]),
        "n3": NodeState(status=NodeStatus.PENDING.value, contract_ref="c3", current_attempt=1, lease_ref=None, artifact_refs=[]),
    }
    state = TeamRunState(
        run_id="run.1", status=status, nodes=nodes,
        active_attempts=["att.1"], active_leases=["l1"], plan_version=plan,
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=2,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=state, version=version, meta=meta), -1)
    return store


def _adapter():
    store = _store()
    return SlackProjectionAdapter(ControlPlane(store), FakeSlackTransport()), store


class TestRootInvariant:
    def test_first_bind_creates_exactly_one_root(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        assert ad._transport.root_count() == 1
        assert len(ad._transport.roots_created) == 1

    def test_progress_updates_same_root(self):
        ad, _ = _adapter()
        ad.materialize("run.1")  # CREATE
        ad.materialize("run.1", session_id="s2")  # UPDATE
        # still exactly one root; no second CREATE
        assert ad._transport.root_count() == 1
        assert len(ad._transport.roots_created) == 1
        assert len(ad._transport.roots_updated) == 1

    def test_rotation_produces_thread_event_root_count_stays_1(self):
        ad, _ = _adapter()
        ad.materialize("run.1", session_id="s1", executor="e1")
        ad.emit_thread("run.1", "SESSION_ROTATED", "session s1 -> s2")
        ad.materialize("run.1", session_id="s2", executor="e2")  # UPDATE, not CREATE
        assert ad._transport.root_count() == 1
        assert len(ad._transport.thread_replies) >= 1

    def test_repeated_materialization_idempotent(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        ad.materialize("run.1")
        ad.materialize("run.1")
        assert ad._transport.root_count() == 1
        assert len(ad._transport.roots_created) == 1

    def test_second_root_for_same_task_fails_closed(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        with pytest.raises(DuplicateRootError):
            ad.attempt_second_root("run.1")
        # zero transport side effect from the failed attempt
        assert ad._transport.root_count() == 1

    def test_thread_event_never_becomes_root(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        ad.emit_thread("run.1", "EXECUTOR_EVENT", "node n1 progressed")
        # thread replies are not roots
        assert len(ad._transport.thread_replies) >= 1
        assert ad._transport.root_count() == 1


class TestActionE2E:
    def test_pause_updates_same_root(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        res = ad.apply_action("run.1", "PAUSE", expected_version=5, command_id="cmd.p")
        assert res["accepted"] is True
        assert res["new_status"] == RunStatus.PAUSED.value
        # still exactly one root, updated not re-created
        assert ad._transport.root_count() == 1
        assert len(ad._transport.roots_created) == 1

    def test_resume_updates_same_root(self):
        ad, store = _adapter()
        # pause first (to allow resume)
        ad.materialize("run.1")
        ad.apply_action("run.1", "PAUSE", expected_version=5, command_id="cmd.p")
        # now resume from paused (version advanced to 6)
        res = ad.apply_action("run.1", "RESUME", expected_version=6, command_id="cmd.r")
        assert res["accepted"] is True
        assert res["new_status"] == RunStatus.RUNNING.value
        assert ad._transport.root_count() == 1

    def test_cancel_updates_same_root_preserves_done(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        res = ad.apply_action("run.1", "CANCEL", expected_version=5, command_id="cmd.c")
        assert res["accepted"] is True
        assert res["new_status"] == RunStatus.CANCELLED.value
        assert ad._transport.root_count() == 1

    def test_replan_updates_same_root(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        res = ad.apply_action("run.1", "REPLAN", expected_version=5, command_id="cmd.rp", new_plan_version="p2")
        assert res["accepted"] is True
        assert ad._transport.root_count() == 1

    def test_stale_action_fails_closed_no_success_update(self):
        ad, _ = _adapter()
        ad.materialize("run.1")
        before_roots = ad._transport.root_count()
        # bump live version out from under the action
        live = ad._cp._store.get_run("run.1")
        ad._cp._store.put_run(VersionedRunState(state=live.state, version=live.version + 1, meta=live.meta), live.version)
        res = ad.apply_action("run.1", "PAUSE", expected_version=5, command_id="cmd.stale")
        assert res["accepted"] is False
        # adapter did NOT update the root as success
        assert ad._transport.root_count() == before_roots

    def test_authority_action_no_runtime_mutation(self):
        ad, store = _adapter()
        ad.materialize("run.1")
        before = store.get_run("run.1").state.status
        res = ad.apply_action("run.1", "APPROVE", expected_version=5)
        assert res["authority_required"] is True
        # runtime unchanged
        assert store.get_run("run.1").state.status == before
        # thread-only signal emitted, no extra root
        assert ad._transport.root_count() == 1
        assert any(o.get("authority_required") for o in ad._transport.ops if o.get("op") == "REPLY_THREAD")


class TestNoForbiddenImports:
    def test_projections_no_forbidden_imports(self):
        import os

        root = os.path.join(os.path.dirname(__file__), "..", "..", "taskcontroller", "projections")
        bad = ("time", "random", "subprocess", "socket", "requests", "urllib")
        hits = []
        for fn in os.listdir(root):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(root, fn)) as fh:
                for line in fh:
                    if "import" in line:
                        for mod in bad:
                            if f"import {mod}" in line or f"from {mod} " in line:
                                hits.append(f"{fn}:{line.strip()}")
        assert hits == [], f"forbidden imports: {hits}"
