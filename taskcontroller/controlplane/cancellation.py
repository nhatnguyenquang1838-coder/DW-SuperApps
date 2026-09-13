"""TC-MBX-806 cancellation boundary for the Controller control plane.

Cancellation is a Controller-owned, CAS-backed mutation.  It is deliberately
implemented beside the existing v1 control intent path rather than introducing
a second state authority:

* the run version is the linearization point;
* the cancellation command identity is durable and replayable;
* active lease bindings are revoked in the same state write;
* a terminal state observed before the CAS commit wins the race; and
* late executor results continue through the existing lease/fence validators,
  where the revoked lease is historical evidence and cannot advance state.

No mailbox, Slack, provider or worker side effect is performed here.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from taskcontroller.controlplane.errors import ControlPlaneError, StaleVersionError
from taskcontroller.controlplane.intents import ControlIntent, ControlResult
from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.kernel.control import cancel as kernel_cancel
from taskcontroller.runtime.errors import ConcurrentStateError
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import RuntimeRecord, StateStore


CANCELLATION_JOURNAL_KIND = "cancellation"
CANCELLATION_KEY_PREFIX = "cancel:"
TERMINAL_WON = "TERMINAL_WON"
CANCEL_WON = "CANCEL_WON"
CANCEL_ALREADY_APPLIED = "CANCEL_ALREADY_APPLIED"

_TERMINAL_STATUSES = frozenset(
    {
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
    }
)


class CancellationCommandConflictError(ControlPlaneError):
    """The same cancellation command identity was reused with new semantics."""


def classify_cancel_terminal_race(run_status: str) -> str:
    """Classify the next cancellation observation without mutating state.

    The CAS commit, not wall-clock time or Slack arrival order, is the race
    authority.  A terminal run observed before cancellation is committed wins;
    a non-terminal run is eligible for the cancellation CAS; an already
    cancelled run has already had its cancellation winner.
    """

    if run_status in _TERMINAL_STATUSES:
        return TERMINAL_WON
    if run_status == RunStatus.CANCELLED.value:
        return CANCEL_WON
    return "CANCEL_PENDING"


def apply_idempotent_cancellation(
    store: StateStore,
    intent: ControlIntent,
) -> ControlResult:
    """Apply or replay one ``CANCEL`` intent through the existing StateStore.

    The command identity is checked before the expected-version guard so a
    retransmitted command can return its durable result even when its original
    snapshot is stale.  The run CAS is the sole winner selection mechanism.
    """

    if intent.intent != "CANCEL":
        raise CancellationCommandConflictError(
            f"cancellation handler received {intent.intent!r}"
        )

    key = _dedupe_key(intent.command_id)
    fingerprint = _fingerprint(intent)
    prior = _lookup_durable_result(store, intent.run_id, key, fingerprint)
    if prior is not None:
        return prior

    current = store.get_run(intent.run_id)
    if current is None:
        raise ControlPlaneError(f"no such run: {intent.run_id!r}")

    # A terminal or already-cancelled observation is a non-mutating race
    # outcome.  Preserve the historical no-command v1 failure behavior.
    disposition = classify_cancel_terminal_race(current.state.status)
    if disposition == TERMINAL_WON:
        if intent.command_id is None:
            _raise_terminal_winner(current.state.status)
        result = _non_mutating_result(intent, current, TERMINAL_WON)
        _persist_result(store, key, fingerprint, result)
        return result
    if disposition == CANCEL_WON:
        if intent.command_id is None:
            _raise_terminal_winner(current.state.status)
        result = _non_mutating_result(intent, current, CANCEL_ALREADY_APPLIED)
        _persist_result(store, key, fingerprint, result)
        return result

    if current.version != intent.expected_version:
        raise StaleVersionError(
            f"stale expected_version {intent.expected_version} != live "
            f"{current.version} for {intent.run_id!r}"
        )

    new_state, revoked_lease_ids, cancelled_attempt_ids = _cancelled_snapshot(current)
    new_state = _with_durable_result(
        new_state,
        key,
        fingerprint,
        ControlResult(
            intent=intent.intent,
            run_id=intent.run_id,
            accepted=True,
            new_version=current.version + 1,
            status=RunStatus.CANCELLED.value,
            detail=CANCEL_WON,
            command_id=intent.command_id,
        ),
    )

    try:
        committed = store.put_run(new_state, intent.expected_version)
    except ConcurrentStateError as exc:
        # Another terminal/cancel commit linearized first.  Read it back and
        # turn the losing signal into evidence rather than retrying a mutation.
        live = store.get_run(intent.run_id)
        if live is not None:
            live_disposition = classify_cancel_terminal_race(live.state.status)
            if live_disposition == TERMINAL_WON:
                if intent.command_id is None:
                    _raise_terminal_winner(live.state.status)
                result = _non_mutating_result(intent, live, TERMINAL_WON)
                _persist_result(store, key, fingerprint, result)
                return result
            if live_disposition == CANCEL_WON and intent.command_id is not None:
                result = _non_mutating_result(intent, live, CANCEL_ALREADY_APPLIED)
                _persist_result(store, key, fingerprint, result)
                return result
        raise StaleVersionError(str(exc)) from exc

    payload = {
        "command_id": intent.command_id,
        "from_version": intent.expected_version,
        "to_version": committed.version,
        "disposition": CANCEL_WON,
        "revoked_lease_ids": revoked_lease_ids,
        "cancelled_attempt_ids": cancelled_attempt_ids,
    }
    store.journal_append(
        intent.run_id,
        RuntimeRecord(CANCELLATION_JOURNAL_KIND, intent.run_id, payload),
    )
    store.sync_journal_position(intent.run_id, committed.version)
    if intent.command_id is not None:
        store.dedupe_put(
            key,
            _stored_fingerprint(fingerprint, _result_for_commit(intent, committed)),
        )
    return _result_for_commit(intent, committed)


def _result_for_commit(intent: ControlIntent, committed: VersionedRunState) -> ControlResult:
    return ControlResult(
        intent=intent.intent,
        run_id=intent.run_id,
        accepted=True,
        new_version=committed.version,
        status=committed.state.status,
        detail=CANCEL_WON,
        command_id=intent.command_id,
    )


def _non_mutating_result(
    intent: ControlIntent,
    current: VersionedRunState,
    detail: str,
) -> ControlResult:
    return ControlResult(
        intent=intent.intent,
        run_id=intent.run_id,
        accepted=False,
        new_version=current.version,
        status=current.state.status,
        detail=detail,
        command_id=intent.command_id,
    )


def _raise_terminal_winner(status: str) -> None:
    from taskcontroller.controlplane.errors import TerminalRunError

    raise TerminalRunError(
        f"cannot cancel terminal run; terminal winner status={status!r}"
    )


def _dedupe_key(command_id: str | None) -> str | None:
    if command_id is None:
        return None
    return f"{CANCELLATION_KEY_PREFIX}{command_id}"


def _fingerprint(intent: ControlIntent) -> dict[str, Any]:
    return {
        "kind": CANCELLATION_JOURNAL_KIND,
        "intent": intent.intent,
        "run_id": intent.run_id,
        "expected_version": intent.expected_version,
        "command_id": intent.command_id,
        "contracts": [repr(contract) for contract in intent.contracts],
    }


def _stored_fingerprint(
    fingerprint: dict[str, Any],
    result: ControlResult,
) -> dict[str, Any]:
    return {
        "kind": CANCELLATION_JOURNAL_KIND,
        "fingerprint": copy.deepcopy(fingerprint),
        "result": result.to_dict(),
    }


def _lookup_durable_result(
    store: StateStore,
    run_id: str,
    key: str | None,
    fingerprint: dict[str, Any],
) -> ControlResult | None:
    if key is None:
        return None
    current = store.get_run(run_id)
    candidates: list[dict[str, Any]] = []
    if current is not None:
        meta = current.meta
        if isinstance(meta, RuntimeSnapshotMeta):
            candidates.append(meta.dedupe_fingerprints.get(key, {}))
        elif isinstance(meta, dict):
            candidates.append(dict(meta.get("dedupe_fingerprints", {}).get(key, {})))
    candidates.append(dict(store.dedupe_state().get(key, {})))
    for stored in candidates:
        if not stored:
            continue
        if stored.get("fingerprint") != fingerprint:
            raise CancellationCommandConflictError(
                f"conflicting reuse of cancellation command {key!r}"
            )
        raw = stored.get("result")
        if isinstance(raw, dict):
            return ControlResult(
                intent=raw["intent"],
                run_id=raw["run_id"],
                accepted=bool(raw["accepted"]),
                new_version=raw.get("new_version"),
                status=raw.get("status"),
                detail=raw.get("detail"),
                command_id=raw.get("command_id"),
            )
    return None


def _persist_result(
    store: StateStore,
    key: str | None,
    fingerprint: dict[str, Any],
    result: ControlResult,
) -> None:
    if key is None:
        return
    stored = _stored_fingerprint(fingerprint, result)
    store.dedupe_put(key, stored)
    # Terminal-first is evidence-only: the durable command result is kept in
    # the existing dedupe sidecar and must not create a state transition.


def _with_durable_result(
    snapshot: VersionedRunState,
    key: str | None,
    fingerprint: dict[str, Any],
    result: ControlResult,
) -> VersionedRunState:
    if key is None:
        return snapshot
    meta = copy.deepcopy(snapshot.meta)
    stored = _stored_fingerprint(fingerprint, result)
    if isinstance(meta, RuntimeSnapshotMeta):
        meta.dedupe_fingerprints[key] = stored
    elif isinstance(meta, dict):
        dedupe = dict(meta.get("dedupe_fingerprints", {}))
        dedupe[key] = stored
        meta["dedupe_fingerprints"] = dedupe
    return VersionedRunState(
        state=snapshot.state,
        version=snapshot.version,
        meta=meta,
    )


def _cancelled_snapshot(
    current: VersionedRunState,
) -> tuple[VersionedRunState, list[str], list[str]]:
    state = kernel_cancel(current.state)
    meta = copy.deepcopy(current.meta)
    revoked: list[str] = []
    cancelled_attempts: list[str] = []

    if isinstance(meta, RuntimeSnapshotMeta):
        leases: dict[str, WorkLease] = {}
        for lease_id, lease in meta.leases.leases.items():
            if lease.run_id == state.run_id and lease.status == LeaseStatus.ACTIVE.value:
                leases[lease_id] = replace(lease, status=LeaseStatus.REVOKED.value)
                revoked.append(lease_id)
            else:
                leases[lease_id] = lease
        meta.leases = RuntimeLeaseState(leases=leases)
        attempts: dict[str, AttemptRecord] = {}
        for attempt_id, attempt in meta.attempt_registry.items():
            if attempt.run_id == state.run_id and attempt.status not in {
                NodeStatus.DONE.value,
                NodeStatus.CANCELLED.value,
            }:
                attempts[attempt_id] = replace(
                    attempt,
                    current_lease_id=None,
                    status=NodeStatus.CANCELLED.value,
                )
                cancelled_attempts.append(attempt_id)
            else:
                attempts[attempt_id] = attempt
        meta.attempt_registry = attempts
    elif isinstance(meta, dict):
        _cancel_dict_meta(meta, state.run_id, revoked, cancelled_attempts)

    # The public run projection must not advertise any lease as current after
    # cancellation.  The metadata keeps revoked lease objects as evidence.
    state = TeamRunState(
        run_id=state.run_id,
        status=state.status,
        nodes=state.nodes,
        active_attempts=list(state.active_attempts),
        active_leases=[],
        artifact_refs=list(state.artifact_refs),
        last_event_cursor=state.last_event_cursor,
        checkpoint=state.checkpoint,
        plan_version=state.plan_version,
        run_version=state.run_version,
        updated_at=state.updated_at,
    )
    return VersionedRunState(state=state, version=current.version + 1, meta=meta), revoked, cancelled_attempts


def _cancel_dict_meta(
    meta: dict[str, Any],
    run_id: str,
    revoked: list[str],
    cancelled_attempts: list[str],
) -> None:
    leases = meta.get("leases")
    if isinstance(leases, RuntimeLeaseState):
        for lease_id, lease in list(leases.leases.items()):
            if lease.run_id == run_id and lease.status == LeaseStatus.ACTIVE.value:
                leases.leases[lease_id] = replace(lease, status=LeaseStatus.REVOKED.value)
                revoked.append(lease_id)
    elif isinstance(leases, dict):
        for lease_id, raw in list(leases.items()):
            if isinstance(raw, WorkLease) and raw.run_id == run_id and raw.status == LeaseStatus.ACTIVE.value:
                leases[lease_id] = replace(raw, status=LeaseStatus.REVOKED.value)
                revoked.append(lease_id)
            elif isinstance(raw, dict) and raw.get("run_id") == run_id and raw.get("status") == LeaseStatus.ACTIVE.value:
                item = dict(raw)
                item["status"] = LeaseStatus.REVOKED.value
                leases[lease_id] = item
                revoked.append(lease_id)
    attempts = meta.get("attempt_registry")
    if isinstance(attempts, dict):
        for attempt_id, raw in list(attempts.items()):
            run_matches = getattr(raw, "run_id", None) == run_id or (
                isinstance(raw, dict) and raw.get("run_id") == run_id
            )
            if not run_matches:
                continue
            status = getattr(raw, "status", None) if not isinstance(raw, dict) else raw.get("status")
            if status in {NodeStatus.DONE.value, NodeStatus.CANCELLED.value}:
                continue
            if isinstance(raw, AttemptRecord):
                attempts[attempt_id] = replace(
                    raw,
                    current_lease_id=None,
                    status=NodeStatus.CANCELLED.value,
                )
            elif isinstance(raw, dict):
                item = dict(raw)
                item["current_lease_id"] = None
                item["status"] = NodeStatus.CANCELLED.value
                attempts[attempt_id] = item
            cancelled_attempts.append(attempt_id)
