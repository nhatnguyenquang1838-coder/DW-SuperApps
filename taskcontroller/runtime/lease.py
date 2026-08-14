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

from taskcontroller.domain.enums import LeaseStatus, NodeStatus
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.domain.values import EventCursor, NodeState
from taskcontroller.kernel.transitions import validate_node_transition
from taskcontroller.runtime.errors import LeaseConflictError, ConcurrentStateError
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    StreamWatermark,
    VersionedRunState,
)
from taskcontroller.runtime.store import StateStore, RuntimeRecord


def _safe_to_dict(obj: Any) -> Any:
    """Convert to dict safely, handling None and missing to_dict."""
    if obj is None:
        return None
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except AttributeError:
            # WorkLease.to_dict fails when holder is None; build dict manually
            if isinstance(obj, WorkLease):
                d: dict[str, Any] = {
                    "lease_id": obj.lease_id,
                    "run_id": obj.run_id,
                    "node_id": obj.node_id,
                    "execution_id": obj.execution_id,
                    "attempt_id": obj.attempt_id,
                    "holder": obj.holder.to_dict() if obj.holder is not None else None,
                    "fencing_token": obj.fencing_token,
                    "granted_at": obj.granted_at,
                    "expires_at": obj.expires_at,
                    "status": obj.status,
                }
                if obj.resource_ref is not None:
                    d["resource_ref"] = obj.resource_ref
                return d
            raise
    return obj


def _leases_from_meta(meta: Any) -> dict[str, WorkLease]:
    """Extract leases as plain dict from meta (RuntimeSnapshotMeta, dict, or RuntimeLeaseState)."""
    if isinstance(meta, RuntimeSnapshotMeta):
        return dict(meta.leases.leases)
    if isinstance(meta, dict):
        leases_raw = meta.get("leases", {})
        if isinstance(leases_raw, RuntimeLeaseState):
            return dict(leases_raw.leases)
        if isinstance(leases_raw, dict):
            ld = {}
            for k, v in leases_raw.items():
                if isinstance(v, WorkLease):
                    ld[k] = v
                elif isinstance(v, dict):
                    ld[k] = WorkLease.from_dict(v)
            return ld
    return {}


def _jp(meta: Any) -> int:
    """Return the current journal_position from a meta (RuntimeSnapshotMeta or dict)."""
    if isinstance(meta, RuntimeSnapshotMeta):
        return meta.journal_position
    if isinstance(meta, dict):
        return int(meta.get("journal_position", 0))
    return 0


def _meta_to_dict(meta: Any) -> dict[str, Any]:
    """Coerce any meta into a plain dict suitable for building VersionedRunState.meta."""
    if isinstance(meta, RuntimeSnapshotMeta):
        return {
            "attempt_registry": {
                k: _safe_to_dict(v) for k, v in meta.attempt_registry.items()
            },
            "leases": {
                k: _safe_to_dict(v) for k, v in meta.leases.leases.items()
            },
            "stream_watermarks": {
                k: _safe_to_dict(v)
                for k, v in meta.stream_watermarks.items()
            },
            "event_cursor": (
                meta.event_cursor.to_dict() if meta.event_cursor else None
            ),
            "dedupe_fingerprints": dict(meta.dedupe_fingerprints),
            "journal_position": meta.journal_position,
        }
    if isinstance(meta, dict):
        return dict(meta)
    return {}


def _dict_to_meta(meta_dict: dict[str, Any]) -> RuntimeSnapshotMeta:
    """Convert a plain meta dict back to RuntimeSnapshotMeta."""
    return RuntimeSnapshotMeta(
        attempt_registry={
            k: v if isinstance(v, AttemptRecord) else AttemptRecord.from_dict(v)
            for k, v in meta_dict.get("attempt_registry", {}).items()
        },
        leases=RuntimeLeaseState(
            leases={
                k: v if isinstance(v, WorkLease) else WorkLease.from_dict(v)
                for k, v in meta_dict.get("leases", {}).items()
            }
        ),
        stream_watermarks={
            k: v if isinstance(v, StreamWatermark) else StreamWatermark.from_dict(v)
            for k, v in meta_dict.get("stream_watermarks", {}).items()
        },
        event_cursor=(
            EventCursor.from_dict(meta_dict["event_cursor"])
            if meta_dict.get("event_cursor")
            else None
        ),
        dedupe_fingerprints=dict(meta_dict.get("dedupe_fingerprints", {})),
        journal_position=meta_dict.get("journal_position", 0),
    )


def _rebuild_versioned_run(
    state: TeamRunState,
    version: int,
    meta: dict[str, Any] | RuntimeSnapshotMeta,
) -> VersionedRunState:
    """Build a VersionedRunState from plain components (state may be mutated already)."""
    if isinstance(meta, RuntimeSnapshotMeta):
        return VersionedRunState(state=state, version=version, meta=meta)
    return VersionedRunState(state=state, version=version, meta=_dict_to_meta(meta))


class LeaseManager:
    """Runtime lease lifecycle manager.

    Public contract:
    - grant(): issue a new lease, detach any existing ACTIVE lease for the same
      (run,node,execution,attempt). Updates AttemptRecord, NodeState, TeamRunState.
    - current(): return the current ACTIVE lease for a given attempt, or None.
    - release(): transition an ACTIVE lease to RELEASED.
    - revoke(): transition an ACTIVE lease to REVOKED.
    - expire(): transition an ACTIVE lease to EXPIRED + node to LEASE_EXPIRED.
    - renew(): extend expiry of an ACTIVE lease (fencing_token must match).
    - All mutations go through the store's CAS (VersionedRunState.version).
    """

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def _jp_now(self, run_id: str) -> int:
        """Authoritative journal_position = highest durable record_index.

        Delegates to the store's last_record_index, which returns the last
        RuntimeRecord.record_index (N-1) or -1 when empty. Sole authority is the
        durable journal, NEVER the run/state version (they may diverge).
        """
        return self._store.last_record_index(run_id)

    def _leases_dict(self, current_state: Any) -> dict[str, WorkLease]:
        """Return leases as plain dict[str, WorkLease]."""
        return _leases_from_meta(current_state.meta)

    def _leases_list(self, current_state: Any) -> list[WorkLease]:
        """Return all leases as a list (for iteration)."""
        return list(self._leases_dict(current_state).values())

    def grant(
        self,
        lease: WorkLease,
        expected_version: int,
        current_state: Any,
    ) -> Any:
        """Grant a new lease. Detach any existing ACTIVE lease for same quad.

        Updates AttemptRecord (current_lease_id, fencing_token), NodeState.lease_ref,
        TeamRunState.active_leases. CAS via store.put_run.
        """
        if lease.status != LeaseStatus.ACTIVE.value:
            raise LeaseConflictError(f"cannot grant non-ACTIVE lease: {lease.status}")

        leases = self._leases_dict(current_state)
        existing = self._find_active_lease_in_dict(
            leases,
            lease.run_id,
            lease.node_id,
            lease.execution_id,
            lease.attempt_id,
        )

        # Build the new state incrementally through CAS steps
        version = expected_version
        rs = current_state

        if existing is not None:
            # Step 1: detach existing -> RELEASED
            detached = self._detach_lease(existing, rs, version)
            rs = detached
            version = rs.version
            self._journal_lease(
                rs.state.run_id,
                "detach",
                existing.lease_id,
                rs,
                current_lease_id=None,
            )

        # Step 2: register new lease + update node/attempt/run
        new_rs = self._register_lease_full(lease, rs, version)
        self._journal_lease(
            rs.state.run_id,
            "grant",
            lease.lease_id,
            new_rs,
            fencing_token=lease.fencing_token,
            current_lease_id=lease.lease_id,
            attempt_id=lease.attempt_id,
        )
        return new_rs

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
        else:
            # If the caller passed a non-lease dict (e.g. dedupe fingerprints),
            # fall back to fetching leases from the store.
            if not leases or not any(
                isinstance(v, WorkLease) for v in leases.values()
            ):
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
            raise LeaseConflictError(
                f"cannot release non-ACTIVE lease: {lease.status}"
            )
        if self._is_expired(lease):
            raise LeaseConflictError(
                f"cannot release expired lease {lease_id}"
            )

        updated = WorkLease(
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
        new_leases[lease_id] = updated
        new_meta_dict = _meta_to_dict(current_state.meta)
        new_meta_dict["leases"] = {
            k: _safe_to_dict(v) for k, v in new_leases.items()
        }
        new_rs = _rebuild_versioned_run(
            current_state.state,
            expected_version + 1,
            new_meta_dict,
        )
        self._store.put_run(new_rs, expected_version)
        self._journal_lease(
            lease.run_id,
            "release",
            lease_id,
            new_rs,
            current_lease_id=None,
            attempt_id=lease.attempt_id,
        )
        return self._store.get_run(lease.run_id)

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
            current = self.current(
                lease.run_id,
                lease.node_id,
                lease.execution_id,
                lease.attempt_id,
                leases,
            )
            if current is not None and current.lease_id != lease_id:
                return current_state
            raise LeaseConflictError(
                f"cannot renew non-ACTIVE lease: {lease.status}"
            )
        if lease.fencing_token != fencing_token:
            raise LeaseConflictError(
                f"fencing_token mismatch for lease {lease_id}"
            )
        if self._is_expired(lease):
            raise LeaseConflictError(
                f"cannot renew expired lease {lease_id}"
            )

        updated = WorkLease(
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
        new_leases[lease_id] = updated
        new_meta_dict = _meta_to_dict(current_state.meta)
        new_meta_dict["leases"] = {
            k: _safe_to_dict(v) for k, v in new_leases.items()
        }
        new_rs = _rebuild_versioned_run(
            current_state.state,
            expected_version + 1,
            new_meta_dict,
        )
        self._store.put_run(new_rs, expected_version)
        self._journal_lease(
            lease.run_id,
            "renew",
            lease_id,
            new_rs,
            fencing_token=lease.fencing_token,
            current_lease_id=lease_id,
            expires_at=new_expires_at,
            attempt_id=lease.attempt_id,
        )
        return self._store.get_run(lease.run_id)

    def revoke(
        self,
        lease_id: str,
        expected_version: int,
        current_state: Any,
    ) -> Any:
        """Revoke an ACTIVE lease (transition to REVOKED)."""
        leases = self._leases_dict(current_state)
        lease = leases.get(lease_id)
        if lease is None:
            raise LeaseConflictError(f"unknown lease_id {lease_id}")
        if lease.status != LeaseStatus.ACTIVE.value:
            raise LeaseConflictError(
                f"cannot revoke non-ACTIVE lease: {lease.status}"
            )

        updated = WorkLease(
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
            status=LeaseStatus.REVOKED.value,
        )
        new_leases = dict(leases)
        new_leases[lease_id] = updated
        new_meta_dict = _meta_to_dict(current_state.meta)
        new_meta_dict["leases"] = {
            k: _safe_to_dict(v) for k, v in new_leases.items()
        }
        new_rs = _rebuild_versioned_run(
            current_state.state,
            expected_version + 1,
            new_meta_dict,
        )
        self._store.put_run(new_rs, expected_version)
        self._journal_lease(
            lease.run_id,
            "revoke",
            lease_id,
            new_rs,
            fencing_token=lease.fencing_token,
            current_lease_id=None,
            attempt_id=lease.attempt_id,
        )
        return self._store.get_run(lease.run_id)

    def _journal_lease(
        self,
        run_id: str,
        op: str,
        lease_id: str,
        new_rs: VersionedRunState,
        *,
        fencing_token: str | None = None,
        current_lease_id: str | None = None,
        expires_at: str | None = None,
        node_status: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        """Append a replay-sufficient lease journal record after successful CAS.

        Includes the post-commit version so recovery replay can assert the
        index/version chain deterministically and advance journal_position.
        """
        payload: dict[str, Any] = {
            "op": op,
            "lease_id": lease_id,
            "version": new_rs.version,
        }
        if fencing_token is not None:
            payload["fencing_token"] = fencing_token
        if current_lease_id is not None:
            payload["current_lease_id"] = current_lease_id
        if expires_at is not None:
            payload["expires_at"] = expires_at
        if node_status is not None:
            payload["node_status"] = node_status
        if attempt_id is not None:
            payload["attempt_id"] = attempt_id
        if op == "grant":
            # Record authoritative lease identity so pure replay reconstructs the
            # lease (holder/granted_at/resource_ref/node/run) exactly, independent
            # of any hardcoded default.
            _lease = _leases_from_meta(new_rs.meta).get(lease_id)
            if _lease is not None:
                payload["node_id"] = _lease.node_id
                payload["execution_id"] = _lease.execution_id
                payload["holder"] = _safe_to_dict(_lease.holder)
                payload["granted_at"] = _lease.granted_at
                payload["resource_ref"] = _lease.resource_ref
        self._store.journal_append(
            run_id,
            RuntimeRecord(
                kind="lease",
                run_id=run_id,
                payload=payload,
            ),
        )

    def expire(
        self,
        lease_id: str,
        expected_version: int,
        current_state: Any,
    ) -> Any:
        """Expire a lease: mark EXPIRED.

        If the expired lease is the current ACTIVE lease for the node,
        also transition the node to LEASE_EXPIRED (valid WP1 transition).
        Old/non-current leases are marked EXPIRED without affecting the node.
        """
        leases = self._leases_dict(current_state)
        lease = leases.get(lease_id)
        if lease is None:
            raise LeaseConflictError(f"unknown lease_id {lease_id}")
        if lease.status != LeaseStatus.ACTIVE.value:
            raise LeaseConflictError(
                f"cannot expire non-ACTIVE lease: {lease.status}"
            )

        run_id = lease.run_id
        node_id = lease.node_id
        is_current = self.current(run_id, node_id, lease.execution_id, lease.attempt_id, leases) is not None
        is_current_lease = is_current and self.current(run_id, node_id, lease.execution_id, lease.attempt_id, leases).lease_id == lease_id

        rs = self._store.get_run(run_id)
        if rs is None:
            raise LeaseConflictError("run not found")

        # Build new lease (EXPIRED)
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
            status=LeaseStatus.EXPIRED.value,
        )

        if is_current_lease:
            # Current lease: also transition node to LEASE_EXPIRED
            node = rs.state.nodes.get(node_id)
            if node is None:
                raise LeaseConflictError(f"node {node_id} not found")
            validate_node_transition(node.status, NodeStatus.LEASE_EXPIRED.value)

            new_node = NodeState(
                status=NodeStatus.LEASE_EXPIRED.value,
                contract_ref=node.contract_ref,
                current_attempt=node.current_attempt,
                lease_ref=lease.lease_id,
                artifact_refs=list(node.artifact_refs),
            )
            new_nodes = dict(rs.state.nodes)
            new_nodes[node_id] = new_node
            new_run = TeamRunState(
                run_id=rs.state.run_id,
                status=rs.state.status,
                nodes=new_nodes,
                active_attempts=list(rs.state.active_attempts),
                active_leases=list(rs.state.active_leases),
            )

            old_meta_dict = _meta_to_dict(rs.meta)
            old_meta_dict["leases"] = {
                k: _safe_to_dict(v) for k, v in dict(leases).items()
            }
            old_meta_dict["leases"][lease_id] = _safe_to_dict(updated_lease)

            att_reg = old_meta_dict.get("attempt_registry", {})
            if "att.1" in att_reg:
                att = att_reg["att.1"]
                if isinstance(att, dict):
                    att["status"] = NodeStatus.LEASE_EXPIRED.value
                    att["current_lease_id"] = None
                elif isinstance(att, AttemptRecord):
                    att.status = NodeStatus.LEASE_EXPIRED.value
                    att.current_lease_id = None

            new_rs = _rebuild_versioned_run(
                new_run,
                expected_version + 1,
                old_meta_dict,
            )
        else:
            # Non-current lease: only mark EXPIRED, no node change
            new_leases = dict(leases)
            new_leases[lease_id] = updated_lease
            new_meta_dict = _meta_to_dict(rs.meta)
            new_meta_dict["leases"] = {
                k: _safe_to_dict(v) for k, v in new_leases.items()
            }
            new_rs = _rebuild_versioned_run(
                rs.state,
                expected_version + 1,
                new_meta_dict,
            )

        self._store.put_run(new_rs, expected_version)
        self._journal_lease(
            run_id,
            "expire",
            lease_id,
            new_rs,
            node_status=NodeStatus.LEASE_EXPIRED.value if is_current_lease else None,
            attempt_id=lease.attempt_id,
        )
        # journal_position is SOLELY derived from the durable journal record index.
        self._store.sync_journal_position(run_id, new_rs.version)
        return self._store.get_run(run_id)

    # ---- internal helpers ----

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
        new_meta_dict = _meta_to_dict(current_state.meta)
        new_meta_dict["leases"] = {
            k: _safe_to_dict(v) for k, v in leases.items()
        }
        new_rs = _rebuild_versioned_run(
            current_state.state,
            expected_version + 1,
            new_meta_dict,
        )
        self._store.put_run(new_rs, expected_version)
        # journal_position is SOLELY derived from the durable journal record index.
        self._store.sync_journal_position(current_state.state.run_id, new_rs.version)
        return self._store.get_run(current_state.state.run_id)

    def _register_lease_full(
        self,
        lease: WorkLease,
        current_state: Any,
        expected_version: int,
    ) -> Any:
        """Register a new lease and update AttemptRecord/NodeState/TeamRunState."""
        run_id = lease.run_id
        node_id = lease.node_id
        attempt_id = lease.attempt_id

        # Read fresh state from store
        rs = self._store.get_run(run_id)
        if rs is None:
            raise LeaseConflictError("run not found")

        leases = self._leases_dict(rs)
        leases[lease.lease_id] = lease

        # Update node lease_ref
        node = rs.state.nodes.get(node_id)
        if node is not None:
            new_nodes = dict(rs.state.nodes)
            new_nodes[node_id] = NodeState(
                status=node.status,
                contract_ref=node.contract_ref,
                current_attempt=node.current_attempt,
                lease_ref=lease.lease_id,
                artifact_refs=list(node.artifact_refs),
            )
            # Build new active_leases: only ACTIVE leases + new lease
            new_active = [lid for lid, l in leases.items() if l.status == LeaseStatus.ACTIVE.value]
            new_active.append(lease.lease_id)
            new_active = list(set(new_active))
            new_run = TeamRunState(
                run_id=rs.state.run_id,
                status=rs.state.status,
                nodes=new_nodes,
                active_attempts=list(rs.state.active_attempts),
                active_leases=new_active,
            )
        else:
            new_run = rs.state
            new_active = list(rs.state.active_leases) + [lease.lease_id]
            new_run.active_leases = new_active

        # Update attempt record
        old_meta_dict = _meta_to_dict(rs.meta)
        att_reg = old_meta_dict.get("attempt_registry", {})
        if attempt_id in att_reg:
            att = att_reg[attempt_id]
            if isinstance(att, dict):
                att["current_lease_id"] = lease.lease_id
                att["fencing_token"] = lease.fencing_token
            elif isinstance(att, AttemptRecord):
                att.current_lease_id = lease.lease_id
                att.fencing_token = lease.fencing_token

        old_meta_dict["leases"] = {
            k: _safe_to_dict(v) for k, v in leases.items()
        }

        new_rs = _rebuild_versioned_run(
            new_run,
            expected_version + 1,
            old_meta_dict,
        )
        self._store.put_run(new_rs, expected_version)
        # journal_position is SOLELY derived from the durable journal record index.
        self._store.sync_journal_position(run_id, new_rs.version)
        return self._store.get_run(run_id)

    def _is_expired(self, lease: WorkLease, now: str | None = None) -> bool:
        """Check if lease is past expires_at (compares ISO timestamps lexicographically)."""
        const_now = "2026-08-14T10:00:00Z"
        if now is None:
            now = const_now
        return lease.expires_at < now


def build_runtime_lease_state(
    leases: dict[str, WorkLease] | None = None,
) -> RuntimeLeaseState:
    """Build a RuntimeLeaseState from a dict of lease_id -> WorkLease."""
    return RuntimeLeaseState(leases=dict(leases or {}))
