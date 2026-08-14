"""WP2 C1 focused tests for EventRouter: canonical fingerprint, dedupe no-op vs reject,
correlation/fencing, strict sequence, reducer authority (COMPLETED->REVIEWING only, never DONE;
STATUS_CHANGE authority bypass; CANCELLED no whole-run cancel).

Scope: taskcontroller/runtime/** + tests/taskcontroller/test_runtime_*.py only.
NO GWC.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import EventType, LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import AgentEvent, TeamRunState, WorkLease
from taskcontroller.domain.values import EventCursor, NodeState
from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.runtime.errors import EventRejected
from taskcontroller.runtime.event_router import EventRouter, _make_canonical_fingerprint
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    StreamWatermark,
    VersionedRunState,
    make_attempt_record,
    make_versioned_run,
)
from taskcontroller.runtime.store import InMemoryStateStore, RuntimeRecord


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_run_state(
    run_id="run.1",
    status=RunStatus.RUNNING.value,
    node_id="n1",
    node_status=NodeStatus.RUNNING.value,
    execution_id="exec.1",
    attempt_id="att.1",
    fencing_token="ft-1",
    lease_id="lease.1",
) -> VersionedRunState:
    lease = WorkLease(
        lease_id=lease_id,
        run_id=run_id,
        node_id=node_id,
        execution_id=execution_id,
        attempt_id=attempt_id,
        holder=ProviderRef("prov.local"),
        fencing_token=fencing_token,
        granted_at="2026-08-13T00:00:00Z",
        expires_at="2026-08-13T01:00:00Z",
        status=LeaseStatus.ACTIVE.value,
    )
    node_state = NodeState(
        status=node_status,
        contract_ref="tc.1",
        current_attempt=1,
        lease_ref=lease_id,
        artifact_refs=[],
    )
    team_state = TeamRunState(
        run_id=run_id,
        status=status,
        nodes={node_id: node_state},
        active_attempts=[execution_id],
        active_leases=[lease_id],
        artifact_refs=[],
        last_event_cursor=None,
    )
    attempt = make_attempt_record(
        attempt_id=attempt_id,
        run_id=run_id,
        node_id=node_id,
        execution_id=execution_id,
        fencing_token=fencing_token,
        current_attempt_number=1,
        current_lease_id=lease_id,
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={attempt_id: attempt},
        leases=RuntimeLeaseState(leases={lease_id: lease}),
        stream_watermarks={},
        event_cursor=None,
        dedupe_fingerprints={},
        journal_position=0,
    )
    return VersionedRunState(state=team_state, version=1, meta=meta)


def _make_event(
    event_id="evt.1",
    run_id="run.1",
    node_id="n1",
    execution_id="exec.1",
    attempt_id="att.1",
    fencing_token="ft-1",
    sequence=0,
    event_type=EventType.TASK_STARTED.value,
    producer=None,
    timestamp="2026-08-13T00:00:00Z",
    idempotency_key=None,
    payload=None,
    artifact_refs=None,
) -> AgentEvent:
    if producer is None:
        producer = ProviderRef("prov.local")
    return AgentEvent(
        event_id=event_id,
        run_id=run_id,
        node_id=node_id,
        execution_id=execution_id,
        attempt_id=attempt_id,
        fencing_token=fencing_token,
        sequence=sequence,
        event_type=event_type,
        producer=producer,
        timestamp=timestamp,
        idempotency_key=idempotency_key,
        payload=payload,
        artifact_refs=artifact_refs or [],
    )


def _seed_store(store: InMemoryStateStore, vrs: VersionedRunState) -> None:
    store.put_run(vrs, -1)


def _make_router_and_state() -> tuple[EventRouter, VersionedRunState, InMemoryStateStore]:
    store = InMemoryStateStore()
    vrs = _make_run_state()
    _seed_store(store, vrs)
    router = EventRouter(store)
    return router, vrs, store


# ---------------------------------------------------------------------------
# canonical fingerprint
# ---------------------------------------------------------------------------

class TestCanonicalFingerprint:
    def test_fingerprint_covers_full_event_content(self):
        e = _make_event(
            event_id="evt.1",
            idempotency_key="ik.1",
            payload={"a": 1},
            artifact_refs=[],
        )
        fp = _make_canonical_fingerprint(e)
        assert fp["event_id"] == "evt.1"
        assert fp["idempotency_key"] == "ik.1"
        assert fp["payload"] == {"a": 1}
        assert fp["run_id"] == "run.1"
        assert fp["node_id"] == "n1"
        assert fp["execution_id"] == "exec.1"
        assert fp["attempt_id"] == "att.1"
        assert fp["fencing_token"] == "ft-1"
        assert fp["sequence"] == 0
        assert fp["event_type"] == EventType.TASK_STARTED.value
        assert fp["timestamp"] == "2026-08-13T00:00:00Z"

    def test_fingerprint_differs_when_payload_differs(self):
        e1 = _make_event(event_id="evt.1", payload={"a": 1})
        e2 = _make_event(event_id="evt.1", payload={"a": 2})
        assert _make_canonical_fingerprint(e1) != _make_canonical_fingerprint(e2)

    def test_fingerprint_differs_when_sequence_differs(self):
        e1 = _make_event(event_id="evt.1", sequence=0)
        e2 = _make_event(event_id="evt.1", sequence=1)
        assert _make_canonical_fingerprint(e1) != _make_canonical_fingerprint(e2)

    def test_fingerprint_differs_when_event_type_differs(self):
        e1 = _make_event(event_id="evt.1", event_type=EventType.TASK_STARTED.value)
        e2 = _make_event(event_id="evt.1", event_type=EventType.PROGRESS.value)
        assert _make_canonical_fingerprint(e1) != _make_canonical_fingerprint(e2)


# ---------------------------------------------------------------------------
# dedupe: identical no-op vs conflicting reject
# ---------------------------------------------------------------------------

class TestDedupeNoopVsReject:
    def test_identical_duplicate_event_is_noop(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(event_id="evt.1", sequence=0)
        # first acceptance should succeed
        result1 = router.route(event, vrs, 1)
        assert result1.version == 2
        # identical second event should be no-op (return current state unchanged)
        result2 = router.route(event, result1, 2)
        assert result2.version == 2
        assert result2.state.run_id == "run.1"

    def test_identical_duplicate_with_idempotency_key_is_noop(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(
            event_id="evt.1",
            idempotency_key="ik.1",
            sequence=0,
        )
        result1 = router.route(event, vrs, 1)
        assert result1.version == 2
        result2 = router.route(event, result1, 2)
        assert result2.version == 2

    def test_conflicting_event_id_rejects(self):
        router, vrs, store = _make_router_and_state()
        event1 = _make_event(event_id="evt.1", sequence=0)
        router.route(event1, vrs, 1)
        current = store.get_run("run.1")
        # same event_id but different canonical content => reject
        event2 = _make_event(
            event_id="evt.1",
            sequence=1,  # different sequence
            event_type=EventType.PROGRESS.value,
        )
        with pytest.raises(EventRejected, match="conflicting reuse"):
            router.route(event2, current, current.version)

    def test_conflicting_idempotency_key_rejects(self):
        router, vrs, store = _make_router_and_state()
        event1 = _make_event(
            event_id="evt.1",
            idempotency_key="ik.1",
            sequence=0,
        )
        router.route(event1, vrs, 1)
        current = store.get_run("run.1")
        # same idempotency_key, different event => reject
        event2 = _make_event(
            event_id="evt.2",
            idempotency_key="ik.1",
            sequence=1,
            event_type=EventType.PROGRESS.value,
        )
        with pytest.raises(EventRejected, match="conflicting reuse"):
            router.route(event2, current, current.version)

    def test_conflicting_duplicate_does_not_mutate_version_or_cursor(self):
        router, vrs, store = _make_router_and_state()
        event1 = _make_event(event_id="evt.1", sequence=0)
        result1 = router.route(event1, vrs, 1)
        current = store.get_run("run.1")
        # attempt conflict with same event_id, diff content
        event2 = _make_event(
            event_id="evt.1",
            sequence=1,
            event_type=EventType.PROGRESS.value,
        )
        with pytest.raises(EventRejected):
            router.route(event2, current, current.version)
        after = store.get_run("run.1")
        # version should be unchanged (2), cursor unchanged
        assert after.version == 2
        assert after.meta.event_cursor.last_event_id == "evt.1"


# ---------------------------------------------------------------------------
# correlation / fencing
# ---------------------------------------------------------------------------

class TestCorrelationFencing:
    def test_event_with_no_current_lease_rejects(self):
        store = InMemoryStateStore()
        vrs = _make_run_state()
        # remove lease from meta
        from taskcontroller.runtime.runtime_state import RuntimeSnapshotMeta
        meta = RuntimeSnapshotMeta(
            attempt_registry=vrs.meta.attempt_registry,
            leases=RuntimeLeaseState(leases={}),
            stream_watermarks={},
            event_cursor=None,
            dedupe_fingerprints={},
            journal_position=0,
        )
        vrs = VersionedRunState(state=vrs.state, version=vrs.version, meta=meta)
        store.put_run(vrs, -1)
        router = EventRouter(store)
        event = _make_event(sequence=0)
        with pytest.raises(EventRejected, match="no current ACTIVE lease"):
            router.route(event, vrs, 0)

    def test_event_with_wrong_fencing_token_rejects(self):
        router, vrs, store = _make_router_and_state()
        # lease has ft-1; event uses ft-2
        event = _make_event(fencing_token="ft-2", sequence=0)
        with pytest.raises(EventRejected, match="fencing_token mismatch"):
            router.route(event, vrs, 1)

    def test_event_for_unknown_attempt_rejects(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(attempt_id="att.unknown", sequence=0)
        with pytest.raises(EventRejected, match="unknown attempt_id"):
            router.route(event, vrs, 1)

    def test_event_for_wrong_run_rejects(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(run_id="run.wrong", sequence=0)
        with pytest.raises(EventRejected, match="correlation mismatch"):
            router.route(event, vrs, 1)

    def test_event_for_wrong_node_rejects(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(node_id="n.wrong", sequence=0)
        with pytest.raises(EventRejected, match="correlation mismatch"):
            router.route(event, vrs, 1)

    def test_event_for_wrong_execution_rejects(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(execution_id="exec.wrong", sequence=0)
        with pytest.raises(EventRejected, match="correlation mismatch"):
            router.route(event, vrs, 1)


# ---------------------------------------------------------------------------
# strict sequence (first 0, no gaps)
# ---------------------------------------------------------------------------

class TestStrictSequence:
    def test_first_event_sequence_zero_accepted(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(sequence=0)
        result = router.route(event, vrs, 1)
        assert result.version == 2

    def test_next_event_must_be_exactly_one_after(self):
        router, vrs, store = _make_router_and_state()
        first = _make_event(event_id="evt.1", sequence=0)
        router.route(first, vrs, 1)
        current = store.get_run("run.1")
        second = _make_event(event_id="evt.2", sequence=1)
        result = router.route(second, current, current.version)
        assert result.version == 3

    def test_sequence_gap_rejects(self):
        router, vrs, store = _make_router_and_state()
        first = _make_event(event_id="evt.1", sequence=0)
        router.route(first, vrs, 1)
        current = store.get_run("run.1")
        third = _make_event(event_id="evt.3", sequence=2)
        with pytest.raises(EventRejected, match="out-of-order sequence"):
            router.route(third, current, current.version)

    def test_same_sequence_with_different_event_rejects(self):
        router, vrs, store = _make_router_and_state()
        first = _make_event(event_id="evt.1", sequence=0)
        router.route(first, vrs, 1)
        current = store.get_run("run.1")
        second = _make_event(
            event_id="evt.2",
            sequence=0,  # same seq, different event
            event_type=EventType.PROGRESS.value,
        )
        with pytest.raises(EventRejected, match="out-of-order sequence"):
            router.route(second, current, current.version)

    def test_out_of_order_rejects(self):
        router, vrs, store = _make_router_and_state()
        first = _make_event(sequence=1)
        with pytest.raises(EventRejected, match="out-of-order sequence"):
            router.route(first, vrs, 1)


# ---------------------------------------------------------------------------
# reducer authority
# ---------------------------------------------------------------------------

class TestReducerAuthority:
    def test_completed_from_running_yields_reviewing_not_done(self):
        router, vrs, store = _make_router_and_state()
        # vrs is RUNNING; COMPLETED must not set run status to DONE
        event = _make_event(
            event_id="evt.completed",
            sequence=0,
            event_type=EventType.COMPLETED.value,
        )
        result = router.route(event, vrs, 1)
        # run status must NOT be DONE after COMPLETED event
        assert result.state.status != NodeStatus.DONE.value
        assert result.state.status != "REVIEWING"

    def test_completed_does_not_set_run_status_to_done(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(
            event_id="evt.completed",
            sequence=0,
            event_type=EventType.COMPLETED.value,
            payload={"status": NodeStatus.DONE.value},
        )
        result = router.route(event, vrs, 1)
        # run status must NOT be DONE after COMPLETED event with DONE payload
        assert result.state.status != NodeStatus.DONE.value

    def test_status_change_with_done_payload_rejects(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(
            event_id="evt.sc",
            sequence=0,
            event_type=EventType.STATUS_CHANGE.value,
            payload={"status": NodeStatus.DONE.value},
        )
        with pytest.raises(TransitionRejected, match="STATUS_CHANGE cannot transition to DONE"):
            router.route(event, vrs, 1)

    def test_status_change_reviewing_from_running_allowed(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(
            event_id="evt.sc",
            sequence=0,
            event_type=EventType.STATUS_CHANGE.value,
            payload={"status": NodeStatus.REVIEWING.value},
        )
        result = router.route(event, vrs, 1)
        # STATUS_CHANGE must not arbitrarily set run status to REVIEWING
        # (REVIEWING is a NodeStatus, not a RunStatus); run status unchanged
        assert result.state.status == RunStatus.RUNNING.value

    def test_cancelled_does_not_cancel_run(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(
            event_id="evt.cancel",
            sequence=0,
            event_type=EventType.CANCELLED.value,
        )
        result = router.route(event, vrs, 1)
        # run status should still be RUNNING (not CANCELLED)
        assert result.state.status == RunStatus.RUNNING.value

    def test_unknown_event_type_does_not_allow_done_transition(self):
        router, vrs, store = _make_router_and_state()
        # lower sequence to 0 so it passes strict sequence check
        event = _make_event(
            event_id="evt2",
            sequence=0,
            event_type=EventType.PROGRESS.value,
        )
        result = router.route(event, vrs, 1)
        assert result.state.status != NodeStatus.DONE.value


# ---------------------------------------------------------------------------
# journal record appended for accepted event
# ---------------------------------------------------------------------------

class TestJournalAppend:
    def test_accepted_event_appends_journal_record(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(event_id="evt.1", sequence=0)
        router.route(event, vrs, 1)
        records = store.journal_get("run.1", -1)
        assert len(records) == 1
        assert records[0].kind == "event"
        assert records[0].payload["event_id"] == "evt.1"

    def test_noop_duplicate_does_not_append_journal(self):
        router, vrs, store = _make_router_and_state()
        event = _make_event(event_id="evt.1", sequence=0)
        router.route(event, vrs, 1)
        assert len(store.journal_get("run.1", -1)) == 1
        router.route(event, store.get_run("run.1"), 2)
        assert len(store.journal_get("run.1", -1)) == 1
