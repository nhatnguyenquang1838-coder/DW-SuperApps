"""WP2 predecessor hotfix regression: explicit lease time semantics (NO GWC).

Proves the runtime no longer invents a hidden 'now'. A lease is current before
its expiry and NOT current after expiry, driven purely by an explicit caller
time. release/renew decisions likewise change only from the explicit `now`.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.domain.values import NodeState
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore

_RUN = "run.1"
_NODE = "n1"
_EXEC = "exec.1"
_ATT = "att.1"
_LEASE = "lease.1"
_FENCE = "fence.1"
_BEFORE = "2026-08-14T10:00:00Z"   # explicit: before expiry
_AFTER = "2026-08-21T00:00:00Z"    # explicit: after expiry
_EXPIRES = "2026-08-20T01:00:00Z"


def _lease():
    return WorkLease(
        lease_id=_LEASE,
        run_id=_RUN,
        node_id=_NODE,
        execution_id=_EXEC,
        attempt_id=_ATT,
        holder=ProviderRef(provider_id="prov.1"),
        fencing_token=_FENCE,
        granted_at="2026-08-13T00:00:00Z",
        expires_at=_EXPIRES,
        status=LeaseStatus.ACTIVE.value,
    )


def _store():
    lease = _lease()
    run = TeamRunState(
        run_id=_RUN,
        status=RunStatus.RUNNING.value,
        nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                current_attempt=1, lease_ref=_LEASE, artifact_refs=[])},
        active_attempts=[_ATT],
        active_leases=[_LEASE],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={
            _ATT: make_attempt_record(
                attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
                fencing_token=_FENCE, current_attempt_number=1, current_lease_id=_LEASE,
            )
        },
        leases=RuntimeLeaseState(leases={_LEASE: lease}),
        stream_watermarks={},
        event_cursor=None,
        dedupe_fingerprints={},
        journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return store


class TestExplicitTimeCurrentness:
    def test_current_before_expiry(self):
        mgr = LeaseManager(_store())
        lease = mgr.current(_RUN, _NODE, _EXEC, _ATT, _BEFORE)
        assert lease is not None
        assert lease.lease_id == _LEASE

    def test_not_current_after_expiry(self):
        mgr = LeaseManager(_store())
        lease = mgr.current(_RUN, _NODE, _EXEC, _ATT, _AFTER)
        assert lease is None

    def test_release_blocked_after_expiry(self):
        store = _store()
        mgr = LeaseManager(store)
        with pytest.raises(Exception):
            mgr.release(_LEASE, store.get_run(_RUN).version, store.get_run(_RUN), _AFTER)

    def test_renew_allowed_before_expiry_rejected_after(self):
        store = _store()
        mgr = LeaseManager(store)
        # before expiry: renew succeeds (fencing matches)
        mgr.renew(_LEASE, "2026-08-25T01:00:00Z", _FENCE, store.get_run(_RUN).version,
                  store.get_run(_RUN), _BEFORE)
        # fresh store, lease still expires at _EXPIRES (2026-08-20) < _AFTER (2026-08-21):
        # renew is rejected because the lease is already expired at _AFTER.
        fresh_store = _store()
        fresh = LeaseManager(fresh_store)
        with pytest.raises(Exception):
            fresh.renew(_LEASE, "2026-08-25T01:00:00Z", _FENCE, fresh_store.get_run(_RUN).version,
                        fresh_store.get_run(_RUN), _AFTER)
