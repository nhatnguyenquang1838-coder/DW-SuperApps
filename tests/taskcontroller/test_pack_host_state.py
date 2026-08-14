"""WP7 S1 focused tests: host pack contract + restart-safe host state (NO GWC)."""

from __future__ import annotations

from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.packs.host_state import (
    DEFAULT_EXECUTOR_PROFILE,
    TaskControllerHostConfig,
    TaskControllerHostState,
)
from taskcontroller.projections.adapter import SlackProjectionAdapter
from taskcontroller.projections.binding import BindingRegistry, DuplicateRootError
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


def _snapshot(root="root.run.1", session_id="s1", model=None, executor=None) -> dict:
    return {"run.1#slack": {
        "binding_key": "run.1#slack", "channel": "slack", "root": root,
        "session_id": session_id, "model": model, "executor": executor,
    }}


class TestHostConfig:
    def test_default_executor_profile_is_hermes_cloud(self):
        cfg = TaskControllerHostConfig(run_id="run.1", task_id="t1")
        assert cfg.executor_profile == DEFAULT_EXECUTOR_PROFILE == "HERMES_CLOUD"

    def test_executor_profile_overridable(self):
        cfg = TaskControllerHostConfig(run_id="run.1", task_id="t1", executor_profile="LOCAL")
        assert cfg.executor_profile == "LOCAL"

    def test_binding_key_is_stable_identity(self):
        cfg = TaskControllerHostConfig(run_id="run.1", task_id="t1", projection_target="slack")
        assert cfg.binding_key() == "run.1#slack"


class TestHostStateRoundTrip:
    def test_serialize_restore_is_deterministic(self):
        state = TaskControllerHostState(
            config=TaskControllerHostConfig(run_id="run.1", task_id="t1"),
            binding_snapshot=_snapshot(),
            session_id="s1", model="gpt", executor="e1", checkpoint_version=2,
        )
        payload = state.serialize()
        restored = TaskControllerHostState.restore(payload)
        assert restored == state
        # byte-equivalent: re-serialize and compare
        assert restored.serialize() == payload

    def test_with_metadata_does_not_change_binding(self):
        state = TaskControllerHostState(
            config=TaskControllerHostConfig(run_id="run.1", task_id="t1"),
            binding_snapshot=_snapshot(),
        )
        updated = state.with_metadata(session_id="s9", model="gpt-x")
        assert updated.binding_snapshot == state.binding_snapshot  # identity preserved
        assert updated.session_id == "s9" and updated.model == "gpt-x"

    def test_next_checkpoint_bumps_version(self):
        state = TaskControllerHostState(
            config=TaskControllerHostConfig(run_id="run.1", task_id="t1"),
            binding_snapshot={}, checkpoint_version=3,
        )
        assert state.next_checkpoint().checkpoint_version == 4


class TestSnapshotIdentityVsContent:
    def test_snapshot_key_and_root_are_stable_identity(self):
        snap = _snapshot(root="root.run.1", session_id="s1", model="gpt", executor="e1")
        # top-level key is the stable binding identity (task/run + target)
        assert list(snap.keys()) == ["run.1#slack"]
        entry = snap["run.1#slack"]
        assert entry["binding_key"] == "run.1#slack"
        assert entry["root"] == "root.run.1"  # root identity present
        # session/model/executor are content only (mutable), not part of the key
        assert entry["session_id"] == "s1"
        assert entry["model"] == "gpt"
        assert entry["executor"] == "e1"

    def test_restore_keeps_root_identity_even_when_content_differs(self):
        snap_old = _snapshot(root="root.run.1", session_id="s1", model="gpt", executor="e1")
        snap_new = _snapshot(root="root.run.1", session_id="s9", model="gpt-x", executor="e2")
        reg_old = BindingRegistry.from_snapshot(snap_old)
        reg_new = BindingRegistry.from_snapshot(snap_new)
        # root identity is identical despite different session/model content
        assert reg_old.lookup("run.1#slack").root == reg_new.lookup("run.1#slack").root
        # content differs as expected
        assert reg_old.lookup("run.1#slack").session_id == "s1"
        assert reg_new.lookup("run.1#slack").session_id == "s9"


class TestRestoreIdempotent:
    def test_restore_same_snapshot_twice_equivalent(self):
        snap = _snapshot()
        a = BindingRegistry.from_snapshot(snap)
        b = BindingRegistry.from_snapshot(snap)
        assert a.snapshot() == b.snapshot()
        assert a.lookup("run.1#slack") == b.lookup("run.1#slack")

    def test_hoststate_restore_same_snapshot_twice_equal(self):
        state = TaskControllerHostState(
            config=TaskControllerHostConfig(run_id="run.1", task_id="t1"),
            binding_snapshot=_snapshot(), checkpoint_version=4,
        )
        r1 = TaskControllerHostState.restore(state.serialize())
        r2 = TaskControllerHostState.restore(state.serialize())
        assert r1 == r2


class TestDuplicateRootFailClosed:
    def test_conflicting_root_fails_closed(self):
        reg = BindingRegistry.from_snapshot(_snapshot(root="root.run.1"))
        # a conflicting bind (same key, different root) must fail closed
        with pytest.raises(DuplicateRootError):
            reg.bind("run.1#slack", "slack", "root.OTHER")
        # no mutation: still the original root
        assert reg.lookup("run.1#slack").root == "root.run.1"


class TestRestoredRegistryUsableByAdapter:
    def test_restored_registry_drives_update_root_no_private_hack(self):
        # Build a fresh SlackProjectionAdapter injecting the RESTORED registry
        # (no private-field hacks). It must recognize the existing binding and
        # emit UPDATE_ROOT, not CREATE_ROOT.
        reg = BindingRegistry.from_snapshot(_snapshot(root="root.run.1", session_id="s1"))
        cp = ControlPlane(_store())
        transport = FakeSlackTransport()
        # public constructor only (registry passed in)
        adapter = SlackProjectionAdapter(cp, transport, reg)
        view = adapter.materialize("run.1")  # type: ignore[arg-type]
        # existing binding => UPDATE_ROOT, no new root created
        assert transport.roots_created == []
        assert transport.roots_updated == ["root.run.1"]


import pytest  # noqa: E402
