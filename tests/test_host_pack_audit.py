"""TDD: audit emission in host_pack.py — Phase 1.

Tests that SlackTaskControllerPack emits audit events for the four
state-changing methods: materialize, controller_action, rotate,
checkpoint_host_state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.facade import AuditFacade
from taskcontroller.audit.writer import CheckpointAuditWriter
from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.packs.host_pack import SlackTaskControllerPack
from taskcontroller.packs.host_state import TaskControllerHostConfig
from taskcontroller.projections.transport import FakeSlackTransport
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


class RecordingAuditFacade(AuditFacade):
    """AuditFacade that records every emitted event for assertion."""

    def __init__(self, writer: CheckpointAuditWriter) -> None:
        self._writer = writer
        self.emitted: list[AuditEvent] = []

    def emit(self, event: AuditEvent) -> None:
        self._writer.emit(event)
        self.emitted.append(event)


# -- factories ---------------------------------------------------------

_RUN = "run-test-001"


def _make_store() -> InMemoryStateStore:
    """Create a store with a pre-existing run so materialize/adapter works."""
    nodes = {
        "n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1",
                        current_attempt=1, lease_ref="l1", artifact_refs=[]),
    }
    state = TeamRunState(
        run_id=_RUN, status=RunStatus.RUNNING.value, nodes=nodes,
        active_attempts=["att.1"], active_leases=["l1"], plan_version="p1",
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={},
        journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=state, version=1, meta=meta), -1)
    return store


def _make_config() -> TaskControllerHostConfig:
    return TaskControllerHostConfig(run_id=_RUN, task_id="task-test-001")


def _make_pack(
    config: TaskControllerHostConfig,
    store: InMemoryStateStore,
    audit: AuditFacade,
) -> SlackTaskControllerPack:
    cp = ControlPlane(store)
    transport = FakeSlackTransport()
    return SlackTaskControllerPack(config, cp, transport, audit=audit)


# -- tests -------------------------------------------------------------


class TestHostPackAuditEmission:
    """Verify that the four mutating methods emit audit events."""

    @pytest.fixture
    def audit_store(self, tmp_path: Path) -> Path:
        return tmp_path / "audit.json"

    @pytest.fixture
    def writer(self, audit_store: Path) -> CheckpointAuditWriter:
        return CheckpointAuditWriter(audit_store)

    @pytest.fixture
    def facade(self, writer: CheckpointAuditWriter) -> RecordingAuditFacade:
        return RecordingAuditFacade(writer)

    @pytest.fixture
    def store(self) -> InMemoryStateStore:
        return _make_store()

    @pytest.fixture
    def pack(self, store: InMemoryStateStore, facade: RecordingAuditFacade) -> SlackTaskControllerPack:
        config = _make_config()
        return _make_pack(config, store, facade)

    # -- materialize --------------------------------------------------

    def test_materialize_emits_audit_materialize(self, pack: SlackTaskControllerPack, facade: RecordingAuditFacade) -> None:
        pack.materialize(session_id="s1", model="gpt-4", executor="exec-1")
        self._assert_one_event(facade, "AUDIT_MATERIALIZE")

    # -- controller_action -------------------------------------------

    def test_controller_action_emits_audit_controller_action(self, pack: SlackTaskControllerPack, facade: RecordingAuditFacade) -> None:
        pack.materialize(session_id="s1")  # bind first so controller_action can proceed
        result = pack.controller_action("approve", expected_version=1)
        self._assert_one_event(facade, "AUDIT_CONTROLLER_ACTION")

    # -- rotate ------------------------------------------------------

    def test_rotate_emits_audit_rotate(self, pack: SlackTaskControllerPack, facade: RecordingAuditFacade) -> None:
        pack.materialize(session_id="s1")  # bind first so rotate can proceed
        pack.rotate(session_id="s2", model="claude", executor="exec-2")
        self._assert_one_event(facade, "AUDIT_ROTATE")

    # -- checkpoint_host_state --------------------------------------

    def test_checkpoint_host_state_emits_audit_checkpoint(self, pack: SlackTaskControllerPack, facade: RecordingAuditFacade) -> None:
        pack.materialize(session_id="s1")
        pack.checkpoint_host_state()
        self._assert_one_event(facade, "AUDIT_CHECKPOINT")

    # -- shared assertions -------------------------------------------

    def _assert_one_event(self, facade: RecordingAuditFacade, kind: str) -> None:
        events = facade.emitted
        matching = [e for e in events if e.decision_kind == kind]
        assert len(matching) == 1, f"expected 1 {kind} event, got {len(matching)} in {len(events)} total"
        self._assert_event_fields(matching[0], kind)

    def _assert_event_fields(self, event: AuditEvent, kind: str) -> None:
        # Core fields must be non-empty
        assert event.event_id, "event_id must not be empty"
        assert event.timestamp, "timestamp must not be empty"
        assert event.run_id, "run_id must not be empty"
        assert event.source == "host_pack", f"source must be 'host_pack', got {event.source!r}"
        assert event.decision_kind == kind, f"decision_kind must be {kind!r}, got {event.decision_kind!r}"
        # payload_summary ≤ 300 chars
        assert len(event.payload_summary) <= 300, f"payload_summary too long: {len(event.payload_summary)}"
        # before/after must be dicts
        assert isinstance(event.before, dict), "before must be a dict"
        assert isinstance(event.after, dict), "after must be a dict"
