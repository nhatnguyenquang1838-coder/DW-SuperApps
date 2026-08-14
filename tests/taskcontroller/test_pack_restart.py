"""WP7 S3 focused tests: restart / duplicate-root adversarial E2E (NO GWC, fake transport)."""

from __future__ import annotations

import json

import pytest

from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.packs.host_pack import SlackTaskControllerPack
from taskcontroller.packs.host_state import TaskControllerHostConfig, TaskControllerHostState
from taskcontroller.projections.binding import DuplicateRootError
from taskcontroller.projections.transport import FakeSlackTransport
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


def _store(status=RunStatus.RUNNING.value, version=5):
    nodes = {
        "n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1", current_attempt=1, lease_ref="l1", artifact_refs=[]),
        "n2": NodeState(status=NodeStatus.DONE.value, contract_ref="c2", current_attempt=1, lease_ref=None, artifact_refs=[]),
    }
    state = TeamRunState(
        run_id="run.1", status=status, nodes=nodes,
        active_attempts=["att.1"], active_leases=["l1"], plan_version="p1",
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=2,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=state, version=version, meta=meta), -1)
    return store


def _new_host(state=None, store=None):
    cfg = TaskControllerHostConfig(run_id="run.1", task_id="t1")
    return SlackTaskControllerPack(cfg, ControlPlane(store or _store()), FakeSlackTransport(), host_state=state)


class TestRestartDuplicateRoot:
    def test_host_a_creates_exactly_one_root(self):
        a = _new_host()
        a.materialize(session_id="s1")
        assert a._transport.root_count() == 1
        assert len(a._transport.roots_created) == 1

    def test_persist_then_destroy_then_host_b_updates_same_root(self):
        # 1-2. Host A materializes -> exactly root R, then persists host state.
        a = _new_host()
        a.materialize(session_id="s1")
        persisted = a.checkpoint_host_state()
        # 3. Destroy Host A; construct Host B from restored state (new metadata allowed).
        b = SlackTaskControllerPack.restore(persisted, ControlPlane(_store()), FakeSlackTransport())
        # 4. Host B materializes same run -> UPDATE R, root count stays exactly 1.
        b.materialize(session_id="s9", model="gpt-x", executor="e2")
        # no new root created; existing root updated
        assert b._transport.roots_created == []
        assert b._transport.roots_updated == ["root.run.1"]

    def test_session_rotated_is_thread_reply_under_r(self):
        a = _new_host()
        a.materialize(session_id="s1")
        persisted = a.checkpoint_host_state()
        b = SlackTaskControllerPack.restore(persisted, ControlPlane(_store()), FakeSlackTransport())
        b.materialize(session_id="s9")
        b.rotate(session_id="s9", model="gpt-x", executor="e2")
        kinds = [o["payload"].get("event_kind") for o in b._transport.ops if o["op"] == "REPLY_THREAD"]
        assert "SESSION_ROTATED" in kinds

    def test_deliberate_second_root_fails_closed_zero_side_effect(self):
        a = _new_host()
        a.materialize(session_id="s1")
        # a second-root attempt on the live host must fail closed, zero transport side effect
        before = a._transport.root_count()
        with pytest.raises(DuplicateRootError):
            a.attempt_second_root()
        assert a._transport.root_count() == before
        assert len(a._transport.roots_created) == 1

    def test_restore_same_checkpoint_twice_idempotent(self):
        a = _new_host()
        a.materialize(session_id="s1")
        persisted = a.checkpoint_host_state()
        b1 = SlackTaskControllerPack.restore(persisted, ControlPlane(_store()), FakeSlackTransport())
        b2 = SlackTaskControllerPack.restore(persisted, ControlPlane(_store()), FakeSlackTransport())
        # both restored hosts share the same binding identity and update the same root
        b1.materialize(session_id="s9")
        b2.materialize(session_id="s9")
        assert b1._transport.roots_created == []
        assert b2._transport.roots_created == []
        assert b1._transport.roots_updated == b2._transport.roots_updated == ["root.run.1"]

    def test_conflicting_checkpoint_root_fails_closed(self):
        a = _new_host()
        a.materialize(session_id="s1")
        persisted = a.checkpoint_host_state()
        # corrupt the persisted snapshot to a DIFFERENT root, then restore+bind.
        d = json.loads(persisted.serialize())
        d["binding_snapshot"]["run.1#slack"]["root"] = "root.EVIL"
        bad_state = TaskControllerHostState.from_dict(d)
        b = SlackTaskControllerPack.restore(bad_state, ControlPlane(_store()), FakeSlackTransport())
        # restoring the registry with a different root is fine; attempting to
        # (re)bind the same key to the ORIGINAL root must fail closed.
        with pytest.raises(DuplicateRootError):
            b._adapter._registry.bind("run.1#slack", "slack", "root.run.1")
