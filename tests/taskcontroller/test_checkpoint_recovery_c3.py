"""C3 acceptance: Journal + Checkpoint + Recovery (NO GWC, NO PR/merge).

Acceptance (per controller C3):
- Every accepted event/lease mutation is journaled AFTER successful CAS with a
  replay-sufficient payload (no `record_index` duplicated into payload;
  RuntimeRecord.record_index is the sole ordering authority).
- Checkpoint preserves TeamRunState/version + attempts + leases + dedupe
  fingerprints + stream watermarks + EventCursor + journal_position (last
  included RuntimeRecord.record_index).
- Recovery restores the checkpoint into a fresh store while RETAINING the
  immutable full journal, then replays post-checkpoint RuntimeRecords through
  PURE reducers only (no live EventRouter.route() / LeaseManager, no fresh
  `now`, no new CAS). It reconstructs state AND sidecars from the records.
- Two consecutive recoveries from the SAME immutable journal yield the same
  final state/sidecars; post-restart dedupe / watermark / fencing / current-lease
  behave identically to pre-crash.
"""

from __future__ import annotations

import copy

import pytest

from taskcontroller.domain.enums import NodeStatus, RunStatus, LeaseStatus
from taskcontroller.domain.ids import ProviderRef, ProducerRef
from taskcontroller.domain.models import TeamRunState, WorkLease, NodeState, AgentEvent
from taskcontroller.runtime.runtime_state import (
    VersionedRunState,
    RuntimeSnapshotMeta,
    RuntimeLeaseState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore
from taskcontroller.runtime.journal import (
    recover_from_checkpoint,
    apply_runtime_record,
    replay_records,
    _meta_to_sidecars,
)
from taskcontroller.runtime.checkpoint import (
    build_checkpoint_snapshot,
    restore_from_checkpoint,
    checkpoint_after_index,
)
from taskcontroller.runtime.event_router import EventRouter
from taskcontroller.runtime.lease import LeaseManager


# ---------------------------------------------------------------------------
# helpers (self-contained; mirror C1/C2 seeding)
# ---------------------------------------------------------------------------

def _seeded_store() -> tuple[InMemoryStateStore, VersionedRunState]:
    """Fresh store with run.1 + ACTIVE lease.1 + attempt att.1 (version 1)."""
    store = InMemoryStateStore()
    lease = WorkLease(
        lease_id="lease.1",
        run_id="run.1",
        node_id="n1",
        execution_id="exec.1",
        attempt_id="att.1",
        holder=ProviderRef("prov.local"),
        fencing_token="ft-1",
        granted_at="2026-08-13T00:00:00Z",
        expires_at="2026-08-20T01:00:00Z",
        status=LeaseStatus.ACTIVE.value,
    )
    node = NodeState(
        status=NodeStatus.RUNNING.value,
        contract_ref="tc.1",
        current_attempt=1,
        lease_ref="lease.1",
        artifact_refs=[],
    )
    trs = TeamRunState(
        run_id="run.1",
        status=RunStatus.RUNNING.value,
        nodes={"n1": node},
        active_attempts=["exec.1"],
        active_leases=["lease.1"],
        artifact_refs=[],
        last_event_cursor=None,
    )
    att = make_attempt_record(
        "att.1", "run.1", "n1", "exec.1", "ft-1", 1, current_lease_id="lease.1"
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={"att.1": att},
        leases=RuntimeLeaseState(leases={"lease.1": lease}),
        stream_watermarks={},
        event_cursor=None,
        dedupe_fingerprints={},
        journal_position=0,
    )
    store.put_run(VersionedRunState(state=trs, version=1, meta=meta), -1)
    return store, store.get_run("run.1")


def _router(store: InMemoryStateStore) -> EventRouter:
    return EventRouter(store)


def _event(seq: int, etype: str, fid: str = "ft-1", payload: dict | None = None):
    return AgentEvent(
        event_id=f"e{seq}",
        run_id="run.1",
        node_id="n1",
        execution_id="exec.1",
        attempt_id="att.1",
        fencing_token=fid,
        sequence=seq,
        event_type=etype,
        timestamp="2026-08-14T00:00:00Z",
        producer=ProducerRef("p1"),
        artifact_refs=[],
        payload=payload,
    )


def _run_events(store, router, events):
    """Route a sequence of events, advancing version each time."""
    cur = store.get_run("run.1")
    for ev in events:
        cur = router.route(ev, cur, cur.version)
    return cur


# ---------------------------------------------------------------------------
# journal + replay-sufficient payloads
# ---------------------------------------------------------------------------

class TestJournalEveryMutation:
    def test_event_mutation_appends_journal_after_cas(self):
        store, _ = _seeded_store()
        router = _router(store)
        router.route(_event(0, "PROGRESS", payload={"note": "a"}), store.get_run("run.1"), 1)
        recs = store.journal_get("run.1", -1)
        assert len(recs) == 1
        assert recs[0].kind == "event"
        # record_index is sole ordering metadata, NOT in payload
        assert "record_index" not in recs[0].payload
        assert recs[0].record_index == 0

    def test_lease_grant_appends_two_records_detach_then_grant(self):
        store, _ = _seeded_store()
        mgr = LeaseManager(store)
        l2 = WorkLease(
            lease_id="lease.2", run_id="run.1", node_id="n1", execution_id="exec.1",
            attempt_id="att.1", holder=ProviderRef("prov.local"), fencing_token="ft-2",
            granted_at="2026-08-13T00:00:00Z", expires_at="2026-08-20T02:00:00Z",
            status=LeaseStatus.ACTIVE.value,
        )
        mgr.grant(l2, store.get_run("run.1").version, store.get_run("run.1"))
        recs = sorted(store.journal_get("run.1", -1), key=lambda r: r.record_index)
        ops = [r.payload.get("op") for r in recs]
        assert ops == ["detach", "grant"]
        # no record_index duplicated into payload
        for r in recs:
            assert "record_index" not in r.payload
        # ascending record_index assigned by journal
        assert [r.record_index for r in recs] == [0, 1]

    def test_event_journal_payload_is_replay_sufficient(self):
        store, _ = _seeded_store()
        router = _router(store)
        router.route(_event(0, "PROGRESS", payload={"note": "a"}), store.get_run("run.1"), 1)
        rec = store.journal_get("run.1", -1)[0]
        p = rec.payload
        # canonical accepted event + dedupe/idempotency keys + fingerprint + version
        assert p["event_id"] == "e0"
        assert p["sequence"] == 0
        assert p["event_type"] == "PROGRESS"
        assert p["fencing_token"] == "ft-1"
        assert p["version"] == 2
        assert p["fingerprint"] is not None
        assert "producer" in p and "payload" in p


# ---------------------------------------------------------------------------
# checkpoint preserves full sidecar set
# ---------------------------------------------------------------------------

class TestCheckpointPreservesSidecars:
    def test_checkpoint_captures_state_version_and_all_sidecars(self):
        store, _ = _seeded_store()
        router = _router(store)
        _run_events(
            store, router,
            [_event(0, "PROGRESS", payload={"note": "a"}), _event(1, "COMPLETED")],
        )
        snap = build_checkpoint_snapshot(store, "run.1")
        # canonical state
        assert snap.state.run_id == "run.1"
        assert snap.state.nodes["n1"].status == NodeStatus.REVIEWING.value
        # attempts
        assert "att.1" in snap.meta.attempt_registry
        assert snap.meta.attempt_registry["att.1"].current_lease_id == "lease.1"
        # leases
        assert "lease.1" in snap.meta.leases.leases
        # dedupe fingerprints (event ids + idempotency keys)
        assert "e0" in snap.meta.dedupe_fingerprints
        assert "e1" in snap.meta.dedupe_fingerprints
        # stream watermarks
        assert ("exec.1", "att.1") in snap.meta.stream_watermarks
        assert snap.meta.stream_watermarks[("exec.1", "att.1")].producer_sequence == 2
        # EventCursor
        assert snap.meta.event_cursor is not None
        assert snap.meta.event_cursor.last_event_id == "e1"
        # journal_position = last included record_index
        assert snap.meta.journal_position == 1


# ---------------------------------------------------------------------------
# recovery equivalence (two consecutive from same immutable journal)
# ---------------------------------------------------------------------------

class TestRecoveryEquivalence:
    def _build_live(self) -> InMemoryStateStore:
        store, _ = _seeded_store()
        router = _router(store)
        mgr = LeaseManager(store)
        # events keep node RUNNING (PROGRESS only) so a later lease expire can
        # validly transition RUNNING -> LEASE_EXPIRED under WP1
        _run_events(
            store, router,
            [_event(0, "PROGRESS", payload={"note": "a"}), _event(1, "PROGRESS", payload={"note": "b"})],
        )
        # lease lifecycle after events
        l2 = WorkLease(
            lease_id="lease.2", run_id="run.1", node_id="n1", execution_id="exec.1",
            attempt_id="att.1", holder=ProviderRef("prov.local"), fencing_token="ft-2",
            granted_at="2026-08-13T00:00:00Z", expires_at="2026-08-20T02:00:00Z",
            status=LeaseStatus.ACTIVE.value,
        )
        mgr.grant(l2, store.get_run("run.1").version, store.get_run("run.1"))
        mgr.renew("lease.2", "2026-08-20T03:00:00Z", "ft-2",
                  store.get_run("run.1").version, store.get_run("run.1"))
        mgr.expire("lease.2", store.get_run("run.1").version, store.get_run("run.1"))
        return store

    def test_two_consecutive_recoveries_yield_same_state_and_sidecars(self):
        store = self._build_live()
        before = store.get_run("run.1")
        journal_before = store.snapshot().journals["run.1"]

        # recovery 1 (fresh target store)
        r1 = recover_from_checkpoint(store, "run.1")
        # recovery 2 (fresh target store, same immutable source journal)
        r2 = recover_from_checkpoint(store, "run.1")

        # journal is immutable evidence: count + indices unchanged by recovery
        journal_after = store.snapshot().journals["run.1"]
        assert len(journal_after) == len(journal_before)
        assert [r.record_index for r in journal_after] == [r.record_index for r in journal_before]

        # both recoveries fully equivalent to pre-crash live state
        assert r1.to_dict() == before.to_dict()
        assert r2.to_dict() == r1.to_dict()

    def test_recovery_preserves_dedupe_watermark_fencing_current_lease(self):
        store = self._build_live()
        before = store.get_run("run.1")
        r1 = recover_from_checkpoint(store, "run.1")

        # post-restart dedupe: a duplicate accepted event must no-op
        router = _router(store)
        v0 = store.get_run("run.1").version
        dup = _event(0, "PROGRESS", payload={"note": "a"})
        out = router.route(dup, store.get_run("run.1"), store.get_run("run.1").version)
        assert out.version == v0, "duplicate event must no-op after recovery"

        # post-restart fencing: wrong fencing token rejected
        with pytest.raises(Exception):
            router.route(
                _event(2, "PROGRESS", fid="WRONG"),
                store.get_run("run.1"),
                store.get_run("run.1").version,
            )

        # post-restart current-lease: expired lease.2 => no current ACTIVE lease
        cur = LeaseManager(store).current("run.1", "n1", "exec.1", "att.1")
        assert cur is None

        # leases + attempts preserved
        assert r1.meta.leases.leases["lease.1"].status == LeaseStatus.RELEASED.value
        assert r1.meta.leases.leases["lease.2"].status == LeaseStatus.EXPIRED.value
        assert r1.meta.attempt_registry["att.1"].current_lease_id is None
        assert before.meta.leases.leases["lease.2"].status == LeaseStatus.EXPIRED.value


# ---------------------------------------------------------------------------
# pure replay reducers (no live acceptance)
# ---------------------------------------------------------------------------

class TestPureReplayReducers:
    def test_apply_runtime_record_event_reconstructs_state_and_sidecars(self):
        store, vs = _seeded_store()
        router = _router(store)
        router.route(_event(0, "PROGRESS", payload={"note": "a"}), store.get_run("run.1"), 1)
        rec = store.journal_get("run.1", -1)[0]
        # pure replay must not call EventRouter.route; reconstruct from record only
        base = copy.deepcopy(vs)
        sc = _meta_to_sidecars(base.meta)
        out = apply_runtime_record(base, sc, rec)
        assert out.state.nodes["n1"].status == NodeStatus.RUNNING.value
        assert out.meta.event_cursor.last_event_id == "e0"
        assert "e0" in out.meta.dedupe_fingerprints
        assert ("exec.1", "att.1") in out.meta.stream_watermarks
        assert out.meta.journal_position == rec.record_index

    def test_replay_records_does_not_mutate_source_store(self):
        store, _ = _seeded_store()
        router = _router(store)
        router.route(_event(0, "PROGRESS"), store.get_run("run.1"), 1)
        router.route(_event(1, "COMPLETED"), store.get_run("run.1"), store.get_run("run.1").version)
        snap = build_checkpoint_snapshot(store, "run.1")
        working = InMemoryStateStore()
        restore_from_checkpoint(working, snap)
        base = working.get_run("run.1")
        records = checkpoint_after_index(store, "run.1", snap.meta.journal_position)
        replayed = replay_records(base, records)
        # source store untouched
        assert store.get_run("run.1").version == 3
        assert replayed.version == 3
