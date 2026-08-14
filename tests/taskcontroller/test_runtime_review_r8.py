"""R8 runtime safety review tests for the TaskController lease/restart/recovery path.

Covers the five R8 findings proven on the exact head before fix:
A. timezone-aware timestamp comparison; naive/invalid input fails closed.
B. expire() targets the exact attempt_id, never a hard-coded "att.1".
C. deterministic artifact_refs / active_leases (no set->list) live vs replay.
D. journal grant persists exact expires_at; replay rejects malformed legacy grants.
E. journal_position == durable last record index after every lease op; stale sync rejected.

The dedicated TaskController CI runs this alongside the full suite. No GWC, no
schema/API expansion.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import ArtifactRef, ProducerRef, ProviderRef
from taskcontroller.domain.models import AgentEvent, Artifact, NodeState, TeamRunState, WorkLease
from taskcontroller.domain.values import EventCursor
from taskcontroller.runtime.errors import ConcurrentStateError, LeaseConflictError
from taskcontroller.runtime.event_router import EventRouter
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.journal import (
    recover_from_checkpoint,
    replay_records,
)
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore, RuntimeRecord


_NOW = "2026-08-20T01:00:00Z"
_FENCE = "ft-1"
_NODE = "n1"
_EXEC = "exec.1"
_ATT = "att.7"  # intentionally NOT att.1 (B)


def _lease(lease_id="lease.1", attempt_id=_ATT, expires_at="2026-08-20T02:00:00Z",
           status=LeaseStatus.ACTIVE.value, fencing_token=_FENCE):
    return WorkLease(
        lease_id=lease_id, run_id="run.1", node_id=_NODE,
        execution_id=_EXEC, attempt_id=attempt_id,
        holder=ProviderRef("prov.local"), fencing_token=fencing_token,
        granted_at="2026-08-13T00:00:00Z", expires_at=expires_at, status=status,
    )


def _state(lease=None, node_status=NodeStatus.RUNNING.value):
    lease = lease or _lease()
    node = NodeState(status=node_status, contract_ref="tc.1", current_attempt=1,
                    lease_ref=lease.lease_id, artifact_refs=[])
    att = make_attempt_record(_ATT, "run.1", _NODE, _EXEC, _FENCE, 1,
                              current_lease_id=lease.lease_id)
    meta = RuntimeSnapshotMeta(
        attempt_registry={_ATT: att},
        leases=RuntimeLeaseState(leases={lease.lease_id: lease}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=0,
    )
    run = TeamRunState(run_id="run.1", status=RunStatus.RUNNING.value,
                      nodes={_NODE: node}, active_attempts=[_ATT],
                      active_leases=[lease.lease_id])
    return VersionedRunState(state=run, version=1, meta=meta)


def _mgr():
    store = InMemoryStateStore()
    cur = _state()
    store.put_run(cur, -1)
    return LeaseManager(store), store, store.get_run("run.1")


def _router(store):
    return EventRouter(store)


# ---------------------------------------------------------------------------
# A. timezone-aware timestamp comparison; fail-closed on naive/invalid
# ---------------------------------------------------------------------------
class TestTimestampComparison:
    def test_utc_and_offset_equivalent_not_expired(self):
        mgr, _, _ = _mgr()
        # boundary: expires_at == now (01:00Z) is NOT expired (strict <)
        s = _state(_lease(expires_at="2026-08-20T01:00:00Z"))
        mgr._store.put_run(s, 1)
        cur = mgr.current("run.1", _NODE, _EXEC, _ATT, now=_NOW)
        assert cur is not None, "expires_at == now boundary => not expired"
        assert cur.status == LeaseStatus.ACTIVE.value

    def test_fractional_seconds_compared(self):
        mgr, _, _ = _mgr()
        # 00:59:59.999999Z is strictly before 01:00:00Z now => expired
        s = _state(_lease(expires_at="2026-08-20T00:59:59.999999Z"))
        mgr._store.put_run(s, 1)
        assert mgr.current("run.1", _NODE, _EXEC, _ATT, now=_NOW) is None

    def test_offset_after_now_expires(self):
        mgr, _, _ = _mgr()
        # 00:30+02:00 = 22:30Z previous day, strictly before 01:00Z now => expired
        s = _state(_lease(expires_at="2026-08-20T00:30:00+02:00"))
        mgr._store.put_run(s, 1)
        assert mgr.current("run.1", _NODE, _EXEC, _ATT, now=_NOW) is None

    def test_naive_timestamp_rejected_in_current(self):
        mgr, _, _ = _mgr()
        s = _state(_lease(expires_at="2026-08-20T02:00:00"))  # naive (no tz)
        mgr._store.put_run(s, 1)
        with pytest.raises(LeaseConflictError):
            mgr.current("run.1", _NODE, _EXEC, _ATT, now=_NOW)

    def test_invalid_timestamp_rejected(self):
        mgr, _, _ = _mgr()
        with pytest.raises(LeaseConflictError):
            mgr.current("run.1", _NODE, _EXEC, _ATT, now="not-a-time")

    def test_naive_expires_rejected_on_renew(self):
        # R8 Fix A: renew() must validate new_expires_at with the timezone-aware
        # parser before any mutation. A naive/invalid timestamp fails closed with
        # LeaseConflictError and ZERO state/journal change.
        mgr, store, cur = _mgr()
        before_version = store.get_run("run.1").version
        before_journal = sorted(
            r.record_index for r in store.journal_get("run.1", -1)
        )
        with pytest.raises(LeaseConflictError):
            mgr.renew("lease.1", "2026-08-20T03:00:00", _FENCE,
                      cur.version, cur, now=_NOW)
        # zero mutation: run version and journal length unchanged
        after = store.get_run("run.1")
        assert after.version == before_version
        assert [r.record_index for r in store.journal_get("run.1", -1)] == before_journal
        # lease unchanged
        assert after.meta.leases.leases["lease.1"].expires_at == "2026-08-20T02:00:00Z"


# ---------------------------------------------------------------------------
# B. expire targets exact attempt_id, never hard-coded att.1
# ---------------------------------------------------------------------------
class TestExpireExactAttempt:
    def test_expire_marks_correct_attempt_not_att1(self):
        mgr, store, cur = _mgr()
        mgr.expire("lease.1", cur.version, cur, now=_NOW)
        att = store.get_run("run.1").meta.attempt_registry[_ATT]
        assert att.status == NodeStatus.LEASE_EXPIRED.value
        # untouched att.1 (none exists) - ensure no att.1 side effect
        assert "att.1" not in store.get_run("run.1").meta.attempt_registry

    def test_expire_arbitrary_attempt_id_node_transition(self):
        mgr, store, cur = _mgr()
        mgr.expire("lease.1", cur.version, cur, now=_NOW)
        node = store.get_run("run.1").state.nodes[_NODE]
        assert node.status == NodeStatus.LEASE_EXPIRED.value


# ---------------------------------------------------------------------------
# C. deterministic artifact_refs + active_leases vs replay
# ---------------------------------------------------------------------------
class TestDeterministicOrdering:
    def test_active_leases_deterministic_no_set(self):
        mgr, store, cur = _mgr()
        l2 = _lease(lease_id="lease.2", attempt_id=_ATT)
        cur = mgr.grant(l2, cur.version, cur)
        live = store.get_run("run.1")
        # lease.1 detached (RELEASED) and lease.2 is the sole ACTIVE entry
        assert live.state.active_leases == ["lease.2"]
        # replay from journal must match exactly (deterministic order, no set->list)
        rec = recover_from_checkpoint(store, "run.1")
        assert rec.state.active_leases == live.state.active_leases

    def test_duplicate_inputs_preserve_single_entry(self):
        mgr, store, cur = _mgr()
        l2 = _lease(lease_id="lease.2")
        mgr.grant(l2, cur.version, cur)  # lease.1 -> RELEASED, lease.2 ACTIVE
        rec = recover_from_checkpoint(store, "run.1")
        assert len(rec.state.active_leases) == len(set(rec.state.active_leases))

    def test_artifact_refs_deterministic_live_vs_replay(self):
        store, vs = _seeded_with_event_artifacts()
        rec = recover_from_checkpoint(store, "run.1")
        # replay reproduces the exact live ordering (no set->list reordering)
        assert rec.state.artifact_refs == vs.state.artifact_refs
        # determinism: a second independent replay yields the identical order
        rec2 = recover_from_checkpoint(store, "run.1")
        assert rec2.state.artifact_refs == rec.state.artifact_refs


def _seeded_with_event_artifacts():
    store = InMemoryStateStore()
    store.put_run(_state(), -1)
    router = _router(store)
    ev = AgentEvent(event_id="e0", run_id="run.1", node_id=_NODE, execution_id=_EXEC,
                    attempt_id=_ATT, fencing_token=_FENCE, sequence=0,
                    event_type="PROGRESS", timestamp=_NOW,
                    producer=ProducerRef("p1"),
                    artifact_refs=[ArtifactRef("a2"), ArtifactRef("a1")])
    router.route(ev, store.get_run("run.1"), store.get_run("run.1").version)
    return store, store.get_run("run.1")


# ---------------------------------------------------------------------------
# D. journal grant persists exact expires_at; replay rejects malformed grants
# ---------------------------------------------------------------------------
class TestGrantJournalFidelity:
    def test_grant_record_carries_expires_at(self):
        mgr, store, cur = _mgr()
        l2 = _lease(lease_id="lease.2", expires_at="2026-08-20T03:30:00Z")
        mgr.grant(l2, cur.version, cur)
        recs = sorted(store.journal_get("run.1", -1), key=lambda r: r.record_index)
        grant = [r for r in recs if r.payload.get("op") == "grant"][-1]
        assert grant.payload["expires_at"] == "2026-08-20T03:30:00Z"
        assert grant.payload["granted_at"] == "2026-08-13T00:00:00Z"
        assert grant.payload["node_id"] == _NODE

    def test_grant_replay_preserves_exact_fields(self):
        mgr, store, cur = _mgr()
        l2 = _lease(lease_id="lease.2", expires_at="2026-08-20T03:30:00Z")
        mgr.grant(l2, cur.version, cur)
        rec = recover_from_checkpoint(store, "run.1")
        assert rec.meta.leases.leases["lease.2"].expires_at == "2026-08-20T03:30:00Z"
        assert rec.meta.leases.leases["lease.2"].granted_at == "2026-08-13T00:00:00Z"

    def test_malformed_legacy_grant_replay_fails_closed(self):
        # Build a base + a legacy grant record missing expires_at/holder
        base = _state()
        bad = RuntimeRecord(kind="lease", run_id="run.1", payload={
            "op": "grant", "lease_id": "lease.legacy", "version": base.version + 1,
            "attempt_id": _ATT, "fencing_token": _FENCE,
            # missing node_id/execution_id/holder/granted_at/expires_at
        })
        with pytest.raises(Exception):
            replay_records(base, [bad])

    def test_no_hardcoded_fallback_in_production_replay(self):
        import taskcontroller.runtime.journal as J
        src = open(J.__file__).read()
        assert "2026-08-14T00:00:00Z" not in src
        assert "2026-08-15T00:00:00Z" not in src
        assert "provider.replay" not in src


# ---------------------------------------------------------------------------
# E. journal_position == durable last index; stale sync rejected
# ---------------------------------------------------------------------------
class TestJournalPositionSync:
    def test_position_after_grant_release_renew_revoke_expire(self):
        mgr, store, cur = _mgr()
        l2 = _lease(lease_id="lease.2")
        cur = mgr.grant(l2, cur.version, cur)            # lease.1 RELEASED, lease.2 ACTIVE
        cur = mgr.renew("lease.2", "2026-08-20T03:00:00Z", _FENCE, cur.version, cur, now=_NOW)
        cur = mgr.revoke("lease.2", cur.version, cur)    # lease.2 REVOKED
        rs = store.get_run("run.1")
        assert rs.meta.journal_position == store.last_record_index("run.1")

    def test_stale_sync_journal_position_rejected(self):
        mgr, store, cur = _mgr()
        # advance real version
        cur = mgr.revoke("lease.1", cur.version, cur)
        real = store.get_run("run.1")
        # call sync with a STALE expected_version (before the revoke)
        with pytest.raises(ConcurrentStateError):
            store.sync_journal_position("run.1", expected_version=cur.version - 1)
        # real position intact
        assert real.meta.journal_position == store.last_record_index("run.1")

    def test_restore_after_grant_expire_roundtrip(self):
        mgr, store, cur = _mgr()
        l2 = _lease(lease_id="lease.2")
        cur = mgr.grant(l2, cur.version, cur)
        mgr.expire("lease.2", cur.version, cur, now=_NOW)
        rec = recover_from_checkpoint(store, "run.1")
        node = rec.state.nodes[_NODE]
        assert node.status == NodeStatus.LEASE_EXPIRED.value
        # attempt current_lease_id cleared
        assert rec.meta.attempt_registry[_ATT].current_lease_id is None


# ---------------------------------------------------------------------------
# R8B — Final runtime safety closure (gaps 1-3 + coverage)
# ---------------------------------------------------------------------------
class TestR8BReplayIdentityFailClosed:
    def _grant_payload(self, missing=None):
        p = {
            "op": "grant",
            "lease_id": "lease.1",
            "version": 1,
            "fencing_token": _FENCE,
            "current_lease_id": "lease.1",
            "attempt_id": _ATT,
            "node_id": _NODE,
            "execution_id": _EXEC,
            "holder": {"provider": "prov.local"},
            "granted_at": "2026-08-13T00:00:00Z",
            "expires_at": "2026-08-20T02:00:00Z",
            "resource_ref": None,
        }
        if missing:
            del p[missing]
        return p

    def test_malformed_grant_replay_missing_attempt_id_fails_closed(self):
        # Gap 1: missing attempt_id in a grant replay record must raise;
        # no fabricated empty identity.
        rec = RuntimeRecord(
            kind="lease", run_id="run.1",
            payload=self._grant_payload(missing="attempt_id"),
        )
        with pytest.raises(RuntimeError):
            replay_records(_state(), [rec])

    def test_malformed_grant_replay_missing_fencing_token_fails_closed(self):
        # Gap 1: missing fencing_token in a grant replay record must raise;
        # no fabricated empty identity.
        rec = RuntimeRecord(
            kind="lease", run_id="run.1",
            payload=self._grant_payload(missing="fencing_token"),
        )
        with pytest.raises(RuntimeError):
            replay_records(_state(), [rec])


class TestR8BGrantTimestampValidation:
    def _grant_bad(self, granted_at, expires_at):
        return WorkLease(
            lease_id="lease.1", run_id="run.1", node_id=_NODE,
            execution_id=_EXEC, attempt_id=_ATT,
            holder=ProviderRef("prov.local"), fencing_token=_FENCE,
            granted_at=granted_at, expires_at=expires_at,
            status=LeaseStatus.ACTIVE.value,
        )

    def _assert_zero_mutation(self, store, before_version, before_journal):
        after = store.get_run("run.1")
        assert after.version == before_version
        assert [r.record_index for r in store.journal_get("run.1", -1)] == before_journal

    def test_grant_naive_granted_at_rejected(self):
        mgr, store, cur = _mgr()
        bv = store.get_run("run.1").version
        bj = [r.record_index for r in store.journal_get("run.1", -1)]
        with pytest.raises(LeaseConflictError):
            mgr.grant(self._grant_bad("2026-08-13 00:00:00", "2026-08-20T02:00:00Z"),
                      cur.version, cur)
        self._assert_zero_mutation(store, bv, bj)

    def test_grant_naive_expires_at_rejected(self):
        mgr, store, cur = _mgr()
        bv = store.get_run("run.1").version
        bj = [r.record_index for r in store.journal_get("run.1", -1)]
        with pytest.raises(LeaseConflictError):
            mgr.grant(self._grant_bad("2026-08-13T00:00:00Z", "2026-08-20 02:00:00"),
                      cur.version, cur)
        self._assert_zero_mutation(store, bv, bj)

    def test_grant_invalid_timestamp_rejected(self):
        mgr, store, cur = _mgr()
        bv = store.get_run("run.1").version
        bj = [r.record_index for r in store.journal_get("run.1", -1)]
        with pytest.raises(LeaseConflictError):
            mgr.grant(self._grant_bad("not-a-time", "2026-08-20T02:00:00Z"),
                      cur.version, cur)
        self._assert_zero_mutation(store, bv, bj)

    def test_grant_expires_before_granted_rejected(self):
        mgr, store, cur = _mgr()
        bv = store.get_run("run.1").version
        bj = [r.record_index for r in store.journal_get("run.1", -1)]
        with pytest.raises(LeaseConflictError):
            mgr.grant(self._grant_bad("2026-08-20T05:00:00Z", "2026-08-20T02:00:00Z"),
                      cur.version, cur)
        self._assert_zero_mutation(store, bv, bj)


class TestR8BNaturalExpiry:
    def _past_lease(self, lease_id="lease.1"):
        # expires_at BEFORE _NOW (2026-08-20T01:00:00Z) -> genuinely time-expired
        return _lease(lease_id=lease_id, expires_at="2026-08-20T00:30:00Z")

    def test_natural_expiry_marks_node_and_clears_attempt(self):
        mgr, store, cur = _mgr()
        cur = mgr.grant(self._past_lease(), cur.version, cur)  # node bound to lease.1
        cur = mgr.expire("lease.1", cur.version, cur, now=_NOW)
        l = cur.meta.leases.leases["lease.1"]
        assert l.status == LeaseStatus.EXPIRED.value
        node = cur.state.nodes[_NODE]
        assert node.status == NodeStatus.LEASE_EXPIRED.value
        assert cur.meta.attempt_registry[_ATT].current_lease_id is None

    def test_natural_expiry_replay_matches_live(self):
        mgr, store, cur = _mgr()
        cur = mgr.grant(self._past_lease(), cur.version, cur)
        cur = mgr.expire("lease.1", cur.version, cur, now=_NOW)
        rec = recover_from_checkpoint(store, "run.1")
        rl = rec.meta.leases.leases["lease.1"]
        assert rl.status == LeaseStatus.EXPIRED.value
        assert rec.state.nodes[_NODE].status == NodeStatus.LEASE_EXPIRED.value
        assert rec.meta.attempt_registry[_ATT].current_lease_id is None

    def test_stale_active_lease_expiry_no_node_transition(self):
        # A genuinely ACTIVE lease that is NOT the node's currently bound lease
        # must expire WITHOUT transitioning the node or clearing the attempt.
        lease1 = _lease(lease_id="lease.1")
        lease2 = _lease(lease_id="lease.2", expires_at="2026-08-20T00:30:00Z")
        node = NodeState(status=NodeStatus.RUNNING.value, contract_ref="tc.1",
                         current_attempt=1, lease_ref="lease.1", artifact_refs=[])
        att = make_attempt_record(_ATT, "run.1", _NODE, _EXEC, _FENCE, 1,
                                  current_lease_id="lease.1")
        meta = RuntimeSnapshotMeta(
            attempt_registry={_ATT: att},
            leases=RuntimeLeaseState(leases={"lease.1": lease1, "lease.2": lease2}),
            stream_watermarks={}, event_cursor=None,
            dedupe_fingerprints={}, journal_position=0,
        )
        run = TeamRunState(run_id="run.1", status=RunStatus.RUNNING.value,
                           nodes={_NODE: node}, active_attempts=[_ATT],
                           active_leases=["lease.1", "lease.2"])
        vs = VersionedRunState(state=run, version=1, meta=meta)
        store = InMemoryStateStore()
        store.put_run(vs, -1)
        mgr = LeaseManager(store)
        # expire lease.2 which is ACTIVE but not node-bound
        cur = mgr.expire("lease.2", 1, vs, now=_NOW)
        assert cur.meta.leases.leases["lease.2"].status == LeaseStatus.EXPIRED.value
        # node must remain RUNNING (lease.1 still bound)
        assert cur.state.nodes[_NODE].status == NodeStatus.RUNNING.value
        # attempt current_lease_id untouched (still lease.1)
        assert cur.meta.attempt_registry[_ATT].current_lease_id == "lease.1"


class TestR8BJournalPositionPerOp:
    def test_position_after_detach_grant(self):
        mgr, store, cur = _mgr()
        cur = mgr.grant(_lease(lease_id="lease.2"), cur.version, cur)
        assert store.get_run("run.1").meta.journal_position == store.last_record_index("run.1")

    def test_position_after_renew(self):
        mgr, store, cur = _mgr()
        cur = mgr.grant(_lease(lease_id="lease.2"), cur.version, cur)
        cur = mgr.renew("lease.2", "2026-08-20T03:00:00Z", _FENCE, cur.version, cur, now=_NOW)
        assert store.get_run("run.1").meta.journal_position == store.last_record_index("run.1")

    def test_position_after_release(self):
        mgr, store, cur = _mgr()
        cur = mgr.release("lease.1", cur.version, cur, now=_NOW)
        assert store.get_run("run.1").meta.journal_position == store.last_record_index("run.1")

    def test_position_after_revoke(self):
        mgr, store, cur = _mgr()
        cur = mgr.revoke("lease.1", cur.version, cur)
        assert store.get_run("run.1").meta.journal_position == store.last_record_index("run.1")

    def test_position_after_expire(self):
        mgr, store, cur = _mgr()
        cur = mgr.expire("lease.1", cur.version, cur, now=_NOW)
        assert store.get_run("run.1").meta.journal_position == store.last_record_index("run.1")


class TestR8BGrantRoundtrip:
    def test_exact_grant_fields_preserved(self):
        mgr, store, cur = _mgr()
        lease = WorkLease(
            lease_id="lease.2", run_id="run.1", node_id=_NODE,
            execution_id=_EXEC, attempt_id=_ATT,
            holder=ProviderRef("prov.local"), fencing_token="ft-9",
            granted_at="2026-08-13T00:00:00Z", expires_at="2026-08-20T03:00:00Z",
            resource_ref="res.X", status=LeaseStatus.ACTIVE.value,
        )
        cur = mgr.grant(lease, cur.version, cur)
        rec = recover_from_checkpoint(store, "run.1")
        rl = rec.meta.leases.leases["lease.2"]
        assert rl.attempt_id == _ATT
        assert rl.fencing_token == "ft-9"
        assert rl.holder == ProviderRef("prov.local")
        assert rl.granted_at == "2026-08-13T00:00:00Z"
        assert rl.expires_at == "2026-08-20T03:00:00Z"
        assert rl.resource_ref == "res.X"

