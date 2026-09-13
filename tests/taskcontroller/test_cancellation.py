"""TC-MBX-806: idempotent cancellation and terminal-race fencing."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.controlplane.engine import ControlEngine
from taskcontroller.controlplane.intents import ControlIntent
from taskcontroller.controlplane.lease_binding import (
    LeaseFenceDisposition,
    evaluate_result_fence,
)
from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.domain.values import NodeState
from taskcontroller.execution.terminal_result import build_terminal_parent_result
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.interaction.state_advancement import (
    StateAdvancingDisposition,
    validate_state_advancing_write,
)
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


_FIXTURE = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
_NOW = "2026-09-12T22:00:00+07:00"
_EXPIRES = "2026-09-13T00:30:00+07:00"
_FENCE = "fence-806"
_RUN_ID = "run-806"
_NODE_ID = "node-806"
_ATTEMPT_ID = "attempt-806"
_EXECUTION_ID = "exec-806"
_LEASE_ID = "lease-806"


def _node(status: str = NodeStatus.RUNNING.value) -> NodeState:
    return NodeState(
        status=status,
        contract_ref="contract-806",
        current_attempt=1,
        lease_ref=_LEASE_ID,
        artifact_refs=[],
    )


def _lease(
    *,
    status: str = LeaseStatus.ACTIVE.value,
    fencing_token: str = _FENCE,
) -> WorkLease:
    return WorkLease(
        lease_id=_LEASE_ID,
        run_id=_RUN_ID,
        node_id=_NODE_ID,
        execution_id=_EXECUTION_ID,
        attempt_id=_ATTEMPT_ID,
        holder=ProviderRef("hermes-mac"),
        fencing_token=fencing_token,
        granted_at="2026-09-12T21:00:00+07:00",
        expires_at=_EXPIRES,
        resource_ref="resource://lease-806",
        status=status,
    )


def _meta(lease: WorkLease | None = None) -> RuntimeSnapshotMeta:
    active = lease or _lease()
    return RuntimeSnapshotMeta(
        attempt_registry={
            _ATTEMPT_ID: AttemptRecord(
                attempt_id=_ATTEMPT_ID,
                run_id=_RUN_ID,
                node_id=_NODE_ID,
                execution_id=_EXECUTION_ID,
                current_lease_id=active.lease_id,
                fencing_token=active.fencing_token,
                status=NodeStatus.RUNNING.value,
                current_attempt_number=1,
            )
        },
        leases=RuntimeLeaseState(leases={active.lease_id: active}),
        stream_watermarks={},
        event_cursor=None,
        dedupe_fingerprints={},
        journal_position=-1,
    )


def _store(
    *,
    status: str = RunStatus.RUNNING.value,
    version: int = 5,
    lease: WorkLease | None = None,
    store_type: type[InMemoryStateStore] = InMemoryStateStore,
) -> InMemoryStateStore:
    state = TeamRunState(
        run_id=_RUN_ID,
        status=status,
        nodes={_NODE_ID: _node()},
        active_attempts=[_ATTEMPT_ID],
        active_leases=[_LEASE_ID] if lease is not None or status == RunStatus.RUNNING.value else [],
        plan_version="plan-806",
    )
    store = store_type()
    store.put_run(
        VersionedRunState(state=state, version=version, meta=_meta(lease) if lease else RuntimeSnapshotMeta(
            attempt_registry={},
            leases=RuntimeLeaseState(leases={}),
            stream_watermarks={},
            event_cursor=None,
            dedupe_fingerprints={},
            journal_position=-1,
        )),
        -1,
    )
    return store


class _TerminalWinsOnCancellationCAS(InMemoryStateStore):
    """Inject a terminal commit between cancellation read and its CAS write."""

    race_pending = True

    def put_run(self, value: VersionedRunState, expected_version: int) -> VersionedRunState:
        if self.race_pending and value.state.status == RunStatus.CANCELLED.value:
            self.race_pending = False
            live = super().get_run(value.state.run_id)
            assert live is not None
            terminal = VersionedRunState(
                state=replace(live.state, status=RunStatus.COMPLETED.value),
                version=live.version + 1,
                meta=live.meta,
            )
            super().put_run(terminal, live.version)
        return super().put_run(value, expected_version)


def _request() -> V2MailboxEnvelope:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    payload = copy.deepcopy(payload)
    payload["run_id"] = _RUN_ID
    payload["node_id"] = _NODE_ID
    payload["message_id"] = "request-806"
    payload["idempotency_key"] = "request-idem-806"
    payload["execution_identity"].update(
        {
            "run_id": _RUN_ID,
            "node_id": _NODE_ID,
            "attempt_id": _ATTEMPT_ID,
            "fencing_token": _FENCE,
        }
    )
    payload["attempt"].update(
        {
            "attempt_id": _ATTEMPT_ID,
            "fencing_token": _FENCE,
            "lease_expires_at": _EXPIRES,
        }
    )
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _terminal() -> Any:
    normalized = {
        "protocol": "dw.taskcontroller.parent-synthesis/v1",
        "proposed_verdict": "PASS",
        "final_verdict": "PASS",
        "verdict": "PASS",
        "status": "PASS",
        "findings": [],
        "child_refs": [
            {
                "child_id": "child-806",
                "status": "SUCCEEDED",
                "result_digest": "sha256:" + "a" * 64,
                "normalization_digest": "sha256:" + "a" * 64,
                "raw_output_digest": "sha256:" + "b" * 64,
                "child_contract_digest": "sha256:" + "c" * 64,
                "source_digest": "sha256:" + "4" * 64,
                "lens": "implementation",
                "reviewer": "reviewer-806",
            }
        ],
        "child_result_digests": ["sha256:" + "a" * 64],
        "residual_risks": [],
        "unresolved_questions": [],
        "conflicts": [],
        "controller_decision": {
            "decision_id": "decision-806",
            "run_ref": _RUN_ID,
            "decision_type": "COMPLETE",
            "rationale": "terminal result for race testing",
            "evidence_refs": ["artifact://evidence-806"],
        },
    }
    return build_terminal_parent_result(
        _request(),
        normalized,
        message_id="terminal-806",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-806",
    )


def _identity(envelope: V2MailboxEnvelope) -> dict[str, Any]:
    return dict(envelope.execution_identity)


def _cancel(*, command_id: str = "cancel-806", expected_version: int = 5) -> ControlIntent:
    return ControlIntent(
        "CANCEL",
        _RUN_ID,
        expected_version=expected_version,
        command_id=command_id,
    )


def test_cancel_is_durable_idempotent_and_retires_active_fence() -> None:
    store = _store(lease=_lease())
    first = ControlEngine(store).apply(_cancel())

    assert first.accepted is True
    assert first.status == RunStatus.CANCELLED.value
    assert first.new_version == 6
    current = store.get_run(_RUN_ID)
    assert current is not None
    assert current.state.active_leases == []
    assert current.state.nodes[_NODE_ID].status == NodeStatus.CANCELLED.value
    assert current.meta.leases.leases[_LEASE_ID].status == LeaseStatus.REVOKED.value
    assert current.meta.attempt_registry[_ATTEMPT_ID].current_lease_id is None
    assert current.meta.attempt_registry[_ATTEMPT_ID].status == NodeStatus.CANCELLED.value
    records = store.journal_get(_RUN_ID, -1)
    assert [record.kind for record in records] == ["cancellation"]

    # A fresh engine instance proves idempotency is durable in the store, not
    # merely a process-local ControlEngine cache.
    second = ControlEngine(store).apply(_cancel(expected_version=5))
    assert second.to_dict() == first.to_dict()
    assert store.get_run(_RUN_ID).version == 6
    assert [record.kind for record in store.journal_get(_RUN_ID, -1)] == ["cancellation"]


def test_conflicting_reuse_of_cancel_command_id_fails_closed() -> None:
    from taskcontroller.controlplane.cancellation import CancellationCommandConflictError

    store = _store(lease=_lease())
    ControlEngine(store).apply(_cancel(command_id="cancel-conflict"))

    with pytest.raises(CancellationCommandConflictError):
        ControlEngine(store).apply(_cancel(command_id="cancel-conflict", expected_version=6))


def test_terminal_first_wins_without_cancel_mutation() -> None:
    store = _store(status=RunStatus.COMPLETED.value, version=8)
    result = ControlEngine(store).apply(_cancel(command_id="cancel-after-terminal", expected_version=8))

    assert result.accepted is False
    assert result.detail == "TERMINAL_WON"
    assert result.status == RunStatus.COMPLETED.value
    assert result.new_version == 8
    assert store.get_run(_RUN_ID).version == 8
    assert store.journal_get(_RUN_ID, -1) == []

    # The same terminal-first observation is durable and idempotent.
    repeated = ControlEngine(store).apply(
        _cancel(command_id="cancel-after-terminal", expected_version=8)
    )
    assert repeated.to_dict() == result.to_dict()


def test_terminal_commit_between_read_and_cancel_cas_is_evidence_only() -> None:
    store = _store(lease=_lease(), store_type=_TerminalWinsOnCancellationCAS)

    result = ControlEngine(store).apply(
        _cancel(command_id="cancel-cas-loser", expected_version=5)
    )

    assert result.accepted is False
    assert result.detail == "TERMINAL_WON"
    assert result.status == RunStatus.COMPLETED.value
    assert store.get_run(_RUN_ID).state.status == RunStatus.COMPLETED.value
    assert store.journal_get(_RUN_ID, -1) == []


def test_legacy_terminal_cancel_without_command_id_still_fails_closed() -> None:
    from taskcontroller.controlplane.errors import TerminalRunError

    store = _store(status=RunStatus.COMPLETED.value, version=8)
    with pytest.raises(TerminalRunError):
        ControlEngine(store).apply(
            ControlIntent("CANCEL", _RUN_ID, expected_version=8)
        )


def test_cancel_first_makes_late_terminal_evidence_only() -> None:
    store = _store(lease=_lease())
    old_lease = store.get_run(_RUN_ID).meta.leases.leases[_LEASE_ID]
    ControlEngine(store).apply(_cancel(command_id="cancel-race"))

    late = _terminal()
    revoked_lease = store.get_run(_RUN_ID).meta.leases.leases[_LEASE_ID]
    assert old_lease.status == LeaseStatus.ACTIVE.value
    assert revoked_lease.status == LeaseStatus.REVOKED.value
    fence = evaluate_result_fence(late.envelope, revoked_lease, now=_NOW)
    assert fence.disposition == LeaseFenceDisposition.STALE_RESULT.value
    assert fence.advances_state is False
    assert fence.evidence_only is True
    assert "lease_status" in fence.failed_checks

    advancement = validate_state_advancing_write(
        late.envelope,
        current_identity=_identity(late.envelope),
        expected_source_digest=late.envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
        active_lease=revoked_lease,
        lease_now=_NOW,
    )
    assert advancement.disposition == StateAdvancingDisposition.STALE_RESULT.value
    assert advancement.advances_state is False
    assert advancement.evidence_only is True


def test_cancel_first_and_terminal_first_have_one_winner() -> None:
    cancel_store = _store(lease=_lease())
    cancel_result = ControlEngine(cancel_store).apply(
        _cancel(command_id="cancel-wins", expected_version=5)
    )
    assert cancel_result.accepted is True
    assert cancel_store.get_run(_RUN_ID).state.status == RunStatus.CANCELLED.value

    terminal_store = _store(status=RunStatus.COMPLETED.value, version=5)
    terminal_result = ControlEngine(terminal_store).apply(
        _cancel(command_id="terminal-wins", expected_version=5)
    )
    assert terminal_result.detail == "TERMINAL_WON"
    assert terminal_store.get_run(_RUN_ID).state.status == RunStatus.COMPLETED.value


def test_cancelled_state_does_not_retain_an_active_worker_binding() -> None:
    store = _store(lease=_lease())
    before = store.get_run(_RUN_ID)
    ControlEngine(store).apply(_cancel(command_id="cancel-worker"))
    after = store.get_run(_RUN_ID)

    assert before is not None and after is not None
    assert before.meta.leases.leases[_LEASE_ID].status == LeaseStatus.ACTIVE.value
    assert after.meta.leases.leases[_LEASE_ID].status == LeaseStatus.REVOKED.value
    assert after.meta.attempt_registry[_ATTEMPT_ID].current_lease_id is None
    assert after.state.active_leases == []
    assert after.version == before.version + 1
