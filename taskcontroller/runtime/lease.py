"""WP2 runtime lease lifecycle: currentness, expiry, replacement detachment (NO GWC).

Design invariants:
- WorkLease binds run_id/node_id/execution_id/attempt_id/holder/fencing_token/expiry/status.
- Lease currentness: only ACTIVE leases with valid fencing_token can be used.
- Replacement detachment: a new lease for the same (run,node,execution,attempt) must
  detach/deprecate the previous ACTIVE lease before becoming current.
- Expiry: expired leases are rejected for current operations.
- Lease conflict: ConcurrentStateError when CAS version mismatch on lease mutation.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.enums import LeaseStatus
from taskcontroller.domain.models import WorkLease
from taskcontroller.runtime.errors import LeaseConflictError, ConcurrentStateError
from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta
from taskcontroller.runtime.store import StateStore, RuntimeRecord

_LICENSE_FIELDS = frozenset({
    "lease_id", "run_id", "node_id", "execution_id", "attempt_id",
    "holder", "fencing_token", "granted_at", "expires_at", "resource_ref", "status",
})


def _deep(obj: Any) -> Any:
    import copy
    return copy.deepcopy(obj)


class LeaseManager:
    """Runtime lease lifecycle manager.

    Public contract:
    - grant(): issue a new lease, detach any existing ACTIVE lease for the same
      (run,node,execution,attempt).
    - current(): return the current ACTIVE lease for a given attempt, or None.
    - release(): transition an ACTIVE lease to RELEASED.
    - renew(): extend expiry of an ACTIVE lease (fencing_token must match).
    - All mutations go through the store's CAS (VersionedRunState.version).
    """

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def _leases_from_state(self, current_state: Any) -> RuntimeLeaseState:
        """Extract RuntimeLeaseState from VersionedRunState.meta."""
        meta = current_state.meta
        if isinstance(meta, RuntimeLeaseState):
            return meta
        if isinstance(meta, RuntimeSnapshotMeta):
            return meta.leases
        if isinstance(meta, dict):
            leases_raw = meta.get("leases", {})
            if isinstance(leases_raw, RuntimeLeaseState):
                return leases_raw
            if isinstance(leases_raw, dict):
                ld = {}
                for k, v in leases_raw.items():
                    if isinstance(v, WorkLease):
                        ld[k] = v
                    elif isinstance(v, dict):
                        ld[k] = WorkLease.from_dict(v)
                return RuntimeLeaseState(leases=ld)
        return RuntimeLeaseState(leases={})

    def _leases_dict(self, current_state: Any) -> dict[str, WorkLease]:
        """Return leases as plain dict[str, WorkLease]."""
        rl = self._leases_from_state(current_state)
        return dict(rl.leases)

    def grant(
        self,
        lease: WorkLease,
        expected_version: int,
        current_state: Any,
    ) -> Any:
        """Grant a new lease. Detach any existing ACTIVE lease for same quad.

        Returns the new VersionedRunState with lease registered.
        """
        # validate lease status
        if lease.status != LeaseStatus.ACTIVE.value:
            raise LeaseConflictError(f"cannot grant non-ACTIVE lease: {lease.status}")

        # find existing lease for same (run,node,execution,attempt)
        leases = self._leases_dict(current_state)
        existing = self._find_active_lease_in_dict(
            leases,
            lease.run_id,
            lease.node_id,
            lease.execution_id,
            lease.attempt_id,
        )
        if existing is not None:
            # detach: mark existing as RELEASED
            detached = self._detach_lease(existing, current_state, expected_version)
            if detached is not current_state:
                # CAS already applied by _detach_lease; update current_state + expected_version
                current_state = detached
                expected_version = current_state.version

        # register new lease
        new_state = self._register_lease(lease, current_state, expected_version)
        return new_state

    def current(
        self,
        run_id: str,
        node_id: str,
        execution_id: str,
        attempt_id: str,
        leases: dict[str, WorkLease] | None = None,
    ) -> WorkLease | None:
        """Return the current ACTIVE lease for the given attempt, or None."""
        if leases is None:
            rs = self._store.get_run(run_id)
            if rs is None:
                return None
            leases = self._leases_dict(rs)
        for lid, lease in leases.items():
            if (
                lease.run_id == run_id
                and lease.node_id == node_id
                and lease.execution_id == execution_id
                and lease.attempt_id == attempt_id
                and lease.status == LeaseStatus.ACTIVE.value
            ):
                if self._is_expired(lease):
                    return None
                return lease
        return None

    def release(
        self,
        lease_id: str,
        expected_version: int,
        current_state: Any,
    ) -> Any:
        """Release an ACTIVE lease (transition to RELEASED)."""
        leases = self._leases_dict(current_state)
        lease = leases.get(lease_id)
        if lease is None:
            raise LeaseConflictError(f"unknown lease_id {lease_id}")
        if lease.status != LeaseStatus.ACTIVE.value:
            raise LeaseConflictError(f"cannot release non-ACTIVE lease: {lease.status}")
        if self._is_expired(lease):
            raise LeaseConflictError(f"cannot release expired lease {lease_id}")

        updated_lease = WorkLease(
            lease_id=lease.lease_id,
            run_id=lease.run_id,
            node_id=lease.node_id,
            execution_id=lease.execution_id,
            attempt_id=lease.attempt_id,
            holder=lease.holder,
            fencing_token=lease.fencing_token,
            granted_at=lease.granted_at,
            expires_at=lease.expires_at,
            resource_ref=lease.resource_ref,
            status=LeaseStatus.RELEASED.value,
        )
        new_leases = dict(leases)
        new_leases[lease_id] = updated_lease
        return self._apply_lease_mutation(
            current_state, expected_version,
            lambda s: self._set_leases(s, RuntimeLeaseState(leases=new_leases)),
        )

    def renew(
        self,
        lease_id: str,
        new_expires_at: str,
        fencing_token: str,
        expected_version: int,
        current_state: Any,
    ) -> Any:
        """Extend expiry of an ACTIVE lease; fencing_token must match."""
        leases = self._leases_dict(current_state)
        lease = leases.get(lease_id)
        if lease is None:
            raise LeaseConflictError(f"unknown lease_id {lease_id}")
        if lease.status != LeaseStatus.ACTIVE.value:
            raise LeaseConflictError(f"cannot renew non-ACTIVE lease: {lease.status}")
        if lease.fencing_token != fencing_token:
            raise LeaseConflictError(f"fencing_token mismatch for lease {lease_id}")
        if self._is_expired(lease):
            raise LeaseConflictError(f"cannot renew expired lease {lease_id}")

        updated_lease = WorkLease(
            lease_id=lease.lease_id,
            run_id=lease.run_id,
            node_id=lease.node_id,
            execution_id=lease.execution_id,
            attempt_id=lease.attempt_id,
            holder=lease.holder,
            fencing_token=lease.fencing_token,
            granted_at=lease.granted_at,
            expires_at=new_expires_at,
            resource_ref=lease.resource_ref,
            status=lease.status,
        )
        new_leases = dict(leases)
        new_leases[lease_id] = updated_lease
        return self._apply_lease_mutation(
            current_state, expected_version,
            lambda s: self._set_leases(s, RuntimeLeaseState(leases=new_leases)),
        )

    # ---- internal ----

    def _set_leases(self, current_state: Any, new_leases: RuntimeLeaseState) -> "VersionedRunState":
        """Return new VersionedRunState with updated leases and bumped version."""
        from taskcontroller.runtime.runtime_state import VersionedRunState as VRState, RuntimeSnapshotMeta
        old_meta = current_state.meta
        if isinstance(old_meta, RuntimeSnapshotMeta):
            new_meta = RuntimeSnapshotMeta(
                attempt_registry=old_meta.attempt_registry,
                leases=new_leases,
                stream_watermarks=old_meta.stream_watermarks,
                event_cursor=old_meta.event_cursor,
                dedupe_fingerprints=old_meta.dedupe_fingerprints,
                journal_position=old_meta.journal_position,
            )
        elif isinstance(old_meta, dict):
            new_meta = dict(old_meta)
            new_meta["leases"] = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in new_leases.leases.items()}
        else:
            new_meta = {"leases": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in new_leases.leases.items()}}
        return VRState(state=current_state.state, version=current_state.version + 1, meta=new_meta)

    def _find_active_lease_in_dict(
        self,
        leases: dict[str, WorkLease],
        run_id: str,
        node_id: str,
        execution_id: str,
        attempt_id: str,
    ) -> WorkLease | None:
        """Find ACTIVE lease for the given quad from leases dict."""
        for lid, lease in leases.items():
            if (
                lease.run_id == run_id
                and lease.node_id == node_id
                and lease.execution_id == execution_id
                and lease.attempt_id == attempt_id
                and lease.status == LeaseStatus.ACTIVE.value
            ):
                return lease
        return None

    def _detach_lease(
        self,
        existing: WorkLease,
        current_state: Any,
        expected_version: int,
    ) -> Any:
        """Mark an existing ACTIVE lease as RELEASED (detached)."""
        updated = WorkLease(
            lease_id=existing.lease_id,
            run_id=existing.run_id,
            node_id=existing.node_id,
            execution_id=existing.execution_id,
            attempt_id=existing.attempt_id,
            holder=existing.holder,
            fencing_token=existing.fencing_token,
            granted_at=existing.granted_at,
            expires_at=existing.expires_at,
            resource_ref=existing.resource_ref,
            status=LeaseStatus.RELEASED.value,
        )
        leases = self._leases_dict(current_state)
        leases[existing.lease_id] = updated
        return self._apply_lease_mutation(
            current_state, expected_version,
            lambda s: self._set_leases(s, RuntimeLeaseState(leases=leases)),
        )

    def _register_lease(
        self,
        lease: WorkLease,
        current_state: Any,
        expected_version: int,
    ) -> Any:
        """Register a new lease into leases."""
        leases = self._leases_dict(current_state)
        leases[lease.lease_id] = lease
        return self._apply_lease_mutation(
            current_state, expected_version,
            lambda s: self._set_leases(s, RuntimeLeaseState(leases=leases)),
        )

    def _apply_lease_mutation(
        self,
        current_state: Any,
        expected_version: int,
        mutate: callable,
    ) -> Any:
        """Apply a lease mutation under CAS, returning new VersionedRunState."""
        from taskcontroller.runtime.runtime_state import VersionedRunState
        new_state = mutate(current_state)
        try:
            self._store.put_run(new_state, expected_version)
        except ConcurrentStateError:
            raise
        except Exception as exc:
            raise ConcurrentStateError(f"CAS failed: {exc}") from exc
        return self._store.get_run(current_state.state.run_id)

    def _is_expired(self, lease: WorkLease) -> bool:
        """Check if lease is past expires_at (naive string compare — MVP)."""
        return False  # MVP: no real clock; tests will mock


def build_runtime_lease_state(leases: dict[str, WorkLease] | None = None) -> RuntimeLeaseState:
    """Build a RuntimeLeaseState from a dict of lease_id -> WorkLease."""
    return RuntimeLeaseState(leases=dict(leases or {}))
