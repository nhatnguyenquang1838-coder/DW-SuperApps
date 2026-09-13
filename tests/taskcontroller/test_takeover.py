"""TC-MBX-804: lease-generation takeover and compatible AgentInstance routing."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from taskcontroller.controlplane.agent_routing import RoutedMailboxRequest
from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.controlplane.takeover import (
    TakeoverRetirement,
    takeover_bounded_mailbox_request,
)
from taskcontroller.domain.enums import (
    BindingType,
    CostClass,
    Idempotency,
    LeaseStatus,
    NodeStatus,
    ProviderKind,
    RunStatus,
    TrustTier,
)
from taskcontroller.domain.ids import CapabilityRef, ProviderRef
from taskcontroller.domain.models import (
    CapabilityCard,
    ExecutionProviderCard,
    TeamRunState,
    WorkLease,
)
from taskcontroller.domain.values import (
    Binding,
    EnvironmentInfo,
    EnvironmentRequirement,
    NodeState,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.state_advancement import (
    StateAdvancingDisposition,
    validate_state_advancing_write,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore
from taskcontroller.routing.registry import build_registry


_NOW = "2026-09-12T13:00:00Z"
_OLD_GRANT = "2026-09-12T12:00:00Z"
_OLD_EXPIRY = "2026-09-12T14:00:00Z"
_EXPIRED_OLD_EXPIRY = "2026-09-12T12:30:00Z"
_NEW_EXPIRY = "2026-09-12T15:00:00Z"
_RUN = "run-804"
_NODE = "node-804"
_EXECUTION = "execution-804"
_ATTEMPT = "attempt-804"
_OLD_FENCE = "fence-804-old"
_NEW_FENCE = "fence-804-new"
_OLD_AGENT = "agent.old"
_NEW_AGENT = "agent.alternate"

_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "path": "taskcontroller/controlplane/takeover.py",
    "blob_digest": "sha256:" + "1" * 64,
}


def _environment(**overrides: object) -> EnvironmentInfo:
    values: dict[str, object] = {
        "os": "darwin",
        "runtime": "python3.11",
        "arch": "arm64",
        "capabilities": ["git", "pytest"],
        "metadata": {"memory_mb": 4096, "locality": "LOCAL"},
    }
    values.update(overrides)
    return EnvironmentInfo(**values)


def _provider(
    provider_id: str,
    *,
    trust: str = TrustTier.STANDARD.value,
    environment: EnvironmentInfo | None = None,
    capability_id: str = "cap.task",
) -> ExecutionProviderCard:
    return ExecutionProviderCard(
        provider_id=provider_id,
        provider_kind=ProviderKind.AGENT.value,
        capability_refs=[CapabilityRef(capability_id)],
        environment=environment if environment is not None else _environment(),
        bindings=[
            Binding(
                kind=BindingType.HTTP_API.value,
                endpoint_ref=f"https://{provider_id}.invalid/dispatch",
                binding_id=f"{provider_id}.binding",
            )
        ],
        trust_tier=trust,
        cost_class=CostClass.MEDIUM.value,
    )


def _registry():
    capability = CapabilityCard(
        capability_id="cap.task",
        name="bounded task execution",
        version="1.0.0",
        idempotency=Idempotency.IDEMPOTENT.value,
        cost_class=CostClass.MEDIUM.value,
        required_environment=EnvironmentRequirement(),
        supported_binding_types=[BindingType.HTTP_API.value],
    )
    return build_registry(
        [
            _provider(_OLD_AGENT),
            _provider(_NEW_AGENT, trust=TrustTier.TRUSTED.value),
            _provider(
                "agent.incompatible",
                trust=TrustTier.TRUSTED.value,
                environment=_environment(runtime="python3.10"),
            ),
        ],
        [capability],
    )


def _request(**changes: object) -> BoundedMailboxRequest:
    values: dict[str, object] = {
        "message_id": "message-804-old",
        "run_id": _RUN,
        "node_id": _NODE,
        "seq": 10,
        "correlation_id": "correlation-804",
        "contract_id": "contract-804",
        "plan_version": "plan-804",
        "contract_digest": "sha256:" + "2" * 64,
        "boundary_digest": "sha256:" + "3" * 64,
        "source_digest": "sha256:" + "4" * 64,
        "source_manifest_ref": "source-manifest-804",
        "objective": "Execute one bounded logical contract.",
        "scope": {
            "allowed_actions": ["read_repo", "run_tests"],
            "denied_actions": ["deploy", "merge"],
            "writable_targets": ["taskcontroller"],
            "source_roots": ["taskcontroller", "tests/taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "authority_constraints": {
            "denied_actions": ["deploy", "merge"],
            "writable_targets": ["taskcontroller"],
        },
        "acceptance_criteria": (
            "The alternate receives the same logical contract.",
            "The old holder cannot advance state after takeover.",
        ),
        "source_refs": (_SOURCE,),
        "evidence_refs": ("evidence://tc-804",),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "5" * 64,
        },
        "standards_profile_ref": "standards.default/v1",
        "recipient_capability": "cap.task",
        "agent_instance": _OLD_AGENT,
        "environment_requirements": {
            "os": "darwin",
            "runtime": "python3.11",
            "arch": "arm64",
            "capabilities": ["git", "pytest"],
        },
        "attempt_id": _ATTEMPT,
        "attempt_number": 1,
        "lease_generation": 4,
        "fencing_token": _OLD_FENCE,
        "lease_expires_at": _OLD_EXPIRY,
        "idempotency_key": "idem-804-old",
        "producer_namespace": "controller",
        "producer_actor_id": "controller-804",
        "execution_id": _EXECUTION,
    }
    values.update(changes)
    return BoundedMailboxRequest(**values)


def _replacement_request(**changes: object) -> BoundedMailboxRequest:
    values: dict[str, object] = {
        "message_id": "message-804-takeover",
        "seq": 11,
        "lease_generation": 5,
        "fencing_token": _NEW_FENCE,
        "lease_expires_at": _NEW_EXPIRY,
        "idempotency_key": "idem-804-takeover",
        "agent_instance": _OLD_AGENT,
    }
    values.update(changes)
    return _request(**values)


def _lease(
    *,
    lease_id: str = "lease-804-old",
    holder: str = _OLD_AGENT,
    fencing_token: str = _OLD_FENCE,
    expires_at: str = _OLD_EXPIRY,
    status: str = LeaseStatus.ACTIVE.value,
) -> WorkLease:
    return WorkLease(
        lease_id=lease_id,
        run_id=_RUN,
        node_id=_NODE,
        execution_id=_EXECUTION,
        attempt_id=_ATTEMPT,
        holder=ProviderRef(holder),
        fencing_token=fencing_token,
        granted_at=_OLD_GRANT,
        expires_at=expires_at,
        status=status,
    )


def _seed(old_lease: WorkLease) -> tuple[LeaseManager, InMemoryStateStore, VersionedRunState]:
    initial = VersionedRunState(
        state=TeamRunState(
            run_id=_RUN,
            status=RunStatus.RUNNING.value,
            nodes={
                _NODE: NodeState(
                    status=NodeStatus.RUNNING.value,
                    contract_ref="contract-804",
                    current_attempt=1,
                    lease_ref=old_lease.lease_id,
                    artifact_refs=[],
                )
            },
            active_attempts=[_ATTEMPT],
            active_leases=[old_lease.lease_id],
        ),
        version=1,
        meta=RuntimeSnapshotMeta(
            attempt_registry={
                _ATTEMPT: make_attempt_record(
                    _ATTEMPT,
                    _RUN,
                    _NODE,
                    _EXECUTION,
                    old_lease.fencing_token,
                    1,
                    current_lease_id=old_lease.lease_id,
                )
            },
            leases=RuntimeLeaseState(leases={old_lease.lease_id: old_lease}),
            stream_watermarks={},
            event_cursor=None,
            dedupe_fingerprints={},
            journal_position=0,
        ),
    )
    store = InMemoryStateStore()
    store.put_run(initial, -1)
    current = store.get_run(_RUN)
    assert current is not None
    return LeaseManager(store), store, current


def _replacement_lease() -> WorkLease:
    return _lease(
        lease_id="lease-804-new",
        holder=_NEW_AGENT,
        fencing_token=_NEW_FENCE,
        expires_at=_NEW_EXPIRY,
    )


def _stored(store: InMemoryStateStore) -> VersionedRunState:
    current = store.get_run(_RUN)
    assert current is not None
    return current


def _old_terminal_result(
    request: BoundedMailboxRequest,
    *,
    agent_instance: str | None = None,
) -> V2MailboxEnvelope:
    payload = copy.deepcopy(compile_bounded_mailbox_request(request).to_dict())
    agent = agent_instance or request.agent_instance
    result_digest = "sha256:" + "6" * 64
    payload.update(
        {
            "message_id": "result-804-old",
            "seq": 12,
            "direction": "executor_to_controller",
            "message_type": "terminal_result",
            "producer": {
                "namespace": "executor",
                "actor_id": agent,
                "role": "executor",
            },
            "idempotency_key": "idem-result-804-old",
            "payload": {"status": "SUCCEEDED", "result_digest": result_digest},
            "result": {
                "status": "SUCCEEDED",
                "boundary_digest": payload["logical_contract"]["boundary_digest"],
                "result_digest": result_digest,
                "artifact_refs": [],
                "findings": [],
            },
        }
    )
    payload["provenance"].update(
        {"origin": "executor", "agent_instance": agent, "status": "SUCCEEDED"}
    )
    payload["recipient"]["agent_instance"] = agent
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def test_takeover_routes_compatible_agent_and_retires_old_lease_before_grant() -> None:
    old_request = _request()
    old_lease = _lease()
    replacement_request = _replacement_request()
    replacement_lease = _replacement_lease()
    manager, store, current = _seed(old_lease)

    result = takeover_bounded_mailbox_request(
        _registry(),
        old_request,
        old_lease,
        replacement_request,
        replacement_lease,
        lease_manager=manager,
        current_state=current,
        expected_version=current.version,
        retirement=TakeoverRetirement.REVOKE,
        now=_NOW,
        receipt_id="receipt-804-takeover",
        accepted_at=_NOW,
    )

    assert isinstance(result.routed, RoutedMailboxRequest)
    assert result.routed.selected_agent_instance == _NEW_AGENT
    assert result.routed.request.agent_instance == _NEW_AGENT
    assert result.routed.envelope.logical_contract == compile_bounded_mailbox_request(
        old_request
    ).logical_contract
    assert result.retired_status == LeaseStatus.REVOKED.value

    stored = _stored(store)
    assert stored.meta.leases.leases[old_lease.lease_id].status == LeaseStatus.REVOKED.value
    assert stored.meta.leases.leases[replacement_lease.lease_id].status == LeaseStatus.ACTIVE.value
    assert stored.state.nodes[_NODE].lease_ref == replacement_lease.lease_id
    assert stored.meta.attempt_registry[_ATTEMPT].current_lease_id == replacement_lease.lease_id
    assert stored.meta.attempt_registry[_ATTEMPT].fencing_token == _NEW_FENCE
    assert stored.state.active_leases == [replacement_lease.lease_id]


def test_expired_takeover_marks_old_lease_expired_and_rebinds_current_lease() -> None:
    old_lease = _lease(expires_at=_EXPIRED_OLD_EXPIRY)
    replacement_lease = _replacement_lease()
    manager, store, current = _seed(old_lease)

    result = takeover_bounded_mailbox_request(
        _registry(),
        _request(lease_expires_at=_EXPIRED_OLD_EXPIRY),
        old_lease,
        _replacement_request(),
        replacement_lease,
        lease_manager=manager,
        current_state=current,
        expected_version=current.version,
        retirement=TakeoverRetirement.EXPIRE,
        now=_NOW,
        receipt_id="receipt-804-expire",
        accepted_at=_NOW,
    )

    assert result.retired_status == LeaseStatus.EXPIRED.value
    stored = _stored(store)
    assert stored.meta.leases.leases[old_lease.lease_id].status == LeaseStatus.EXPIRED.value
    assert stored.meta.leases.leases[replacement_lease.lease_id].status == LeaseStatus.ACTIVE.value
    assert stored.state.nodes[_NODE].lease_ref == replacement_lease.lease_id


def test_old_result_and_heartbeat_are_non_advancing_after_takeover() -> None:
    old_request = _request()
    old_lease = _lease()
    replacement_lease = _replacement_lease()
    manager, store, current = _seed(old_lease)
    result = takeover_bounded_mailbox_request(
        _registry(),
        old_request,
        old_lease,
        _replacement_request(),
        replacement_lease,
        lease_manager=manager,
        current_state=current,
        expected_version=current.version,
        retirement=TakeoverRetirement.REVOKE,
        now=_NOW,
        receipt_id="receipt-804-stale",
        accepted_at=_NOW,
    )

    old_envelope = _old_terminal_result(old_request)
    current_identity = result.routed.envelope.execution_identity
    decision = validate_state_advancing_write(
        old_envelope,
        current_identity=current_identity,
        expected_source_digest=current_identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
        active_lease=replacement_lease,
        lease_now=_NOW,
    )

    assert decision.disposition == StateAdvancingDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert "lease_generation" in decision.failed_checks

    stored = _stored(store)
    renewed = manager.renew(
        old_lease.lease_id,
        new_expires_at="2026-09-12T18:00:00Z",
        fencing_token=old_lease.fencing_token,
        expected_version=stored.version,
        current_state=stored,
        now=_NOW,
    )
    assert renewed.version == stored.version
    after_heartbeat = _stored(store)
    assert after_heartbeat.meta.leases.leases[old_lease.lease_id].status == LeaseStatus.REVOKED.value
    assert after_heartbeat.meta.leases.leases[replacement_lease.lease_id].expires_at == _NEW_EXPIRY


def test_replacement_passes_active_fence_after_takeover() -> None:
    old_lease = _lease()
    replacement_request = _replacement_request()
    replacement_lease = _replacement_lease()
    manager, store, current = _seed(old_lease)
    result = takeover_bounded_mailbox_request(
        _registry(),
        _request(),
        old_lease,
        replacement_request,
        replacement_lease,
        lease_manager=manager,
        current_state=current,
        expected_version=current.version,
        retirement=TakeoverRetirement.REVOKE,
        now=_NOW,
        receipt_id="receipt-804-current",
        accepted_at=_NOW,
    )

    identity = result.routed.envelope.execution_identity
    replacement_result = _old_terminal_result(
        result.routed.request,
        agent_instance=_NEW_AGENT,
    )
    decision = validate_state_advancing_write(
        replacement_result,
        current_identity=identity,
        expected_source_digest=identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
        active_lease=replacement_lease,
        lease_now=_NOW,
    )

    assert decision.disposition == StateAdvancingDisposition.ACCEPTED.value
    assert decision.advances_state is True
    assert decision.evidence_only is False
    assert _stored(store).meta.leases.leases[replacement_lease.lease_id].status == LeaseStatus.ACTIVE.value


@pytest.mark.parametrize(
    "changes",
    [
        {"lease_generation": 4},
        {"seq": 10},
        {"fencing_token": _OLD_FENCE},
        {"idempotency_key": "idem-804-old"},
        {"attempt_id": "attempt-804-other"},
    ],
)
def test_takeover_rejects_non_new_identity_or_ordering(changes: dict[str, Any]) -> None:
    old_lease = _lease()
    replacement_request = _replacement_request(**changes)
    replacement_lease = _replacement_lease()
    manager, store, current = _seed(old_lease)

    with pytest.raises(TaskControllerValidationError):
        takeover_bounded_mailbox_request(
            _registry(),
            _request(),
            old_lease,
            replacement_request,
            replacement_lease,
            lease_manager=manager,
            current_state=current,
            expected_version=current.version,
            retirement=TakeoverRetirement.REVOKE,
            now=_NOW,
            receipt_id="receipt-804-invalid",
            accepted_at=_NOW,
        )

    assert _stored(store).version == current.version
    assert _stored(store).meta.leases.leases[old_lease.lease_id].status == LeaseStatus.ACTIVE.value
