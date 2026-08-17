from __future__ import annotations

from taskcontroller.audit.event import AuditEvent
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.packs.host_pack import SlackTaskControllerPack
from taskcontroller.packs.host_state import TaskControllerHostConfig
from taskcontroller.projections.transport import FakeSlackTransport
from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta, VersionedRunState
from taskcontroller.runtime.store import InMemoryStateStore

RUN_ID = "run-audit-host-salvage"

class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, run_id: str, event: AuditEvent) -> int:
        assert run_id == event.run_id
        self.events.append(event)
        return len(self.events)

def _store() -> InMemoryStateStore:
    nodes = {"n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1", current_attempt=1, lease_ref="l1", artifact_refs=[])}
    state = TeamRunState(run_id=RUN_ID, status=RunStatus.RUNNING.value, nodes=nodes, active_attempts=["att.1"], active_leases=["l1"], plan_version="p1")
    meta = RuntimeSnapshotMeta(attempt_registry={}, leases=RuntimeLeaseState(leases={}), stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0)
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=state, version=1, meta=meta), -1)
    return store

def _pack(audit: RecordingAudit) -> SlackTaskControllerPack:
    return SlackTaskControllerPack(TaskControllerHostConfig(run_id=RUN_ID, task_id="task-audit-host-salvage"), ControlPlane(_store()), FakeSlackTransport(), audit=audit)

def _event(audit: RecordingAudit, kind: str) -> AuditEvent:
    matches = [event for event in audit.events if event.decision_kind == kind]
    assert len(matches) == 1
    event = matches[0]
    assert event.source == "host_pack"
    assert event.run_id == RUN_ID
    assert event.event_id
    assert event.timestamp
    assert len(event.payload_summary) <= 300
    return event

def test_materialize_records_semantic_audit_event() -> None:
    audit = RecordingAudit()
    pack = _pack(audit)
    pack.materialize(session_id="s1", model="gpt", executor="hermes-cloud")
    event = _event(audit, "HOST_MATERIALIZED")
    assert event.after["session_id"] == "s1"
    assert event.after["executor"] == "hermes-cloud"

def test_controller_action_records_semantic_audit_event() -> None:
    audit = RecordingAudit()
    pack = _pack(audit)
    pack.materialize(session_id="s1")
    pack.controller_action("approve", expected_version=1)
    event = _event(audit, "HOST_CONTROLLER_ACTION")
    assert event.before["action"] == "approve"
    assert event.before["expected_version"] == 1

def test_rotate_records_true_before_and_after_metadata() -> None:
    audit = RecordingAudit()
    pack = _pack(audit)
    pack.materialize(session_id="s1", model="gpt", executor="hermes-cloud")
    pack.rotate(session_id="s2", model="claude", executor="hermes-mac")
    event = _event(audit, "HOST_ROTATED")
    assert event.before == {"session_id": "s1", "model": "gpt", "executor": "hermes-cloud"}
    assert event.after == {"session_id": "s2", "model": "claude", "executor": "hermes-mac"}

def test_checkpoint_records_version_transition() -> None:
    audit = RecordingAudit()
    pack = _pack(audit)
    pack.materialize(session_id="s1")
    checkpoint = pack.checkpoint_host_state()
    event = _event(audit, "HOST_CHECKPOINTED")
    assert event.before["checkpoint_version"] == checkpoint.checkpoint_version - 1
    assert event.after["checkpoint_version"] == checkpoint.checkpoint_version
