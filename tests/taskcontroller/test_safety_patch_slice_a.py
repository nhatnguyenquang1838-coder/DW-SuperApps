from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from taskcontroller.compiler import compile_blueprint
from taskcontroller.domain.enums import BindingType, LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import (
    ExecutionProviderCard,
    ExecutionReceipt,
    ExecutionRequest,
    TeamRunState,
    WorkLease,
)
from taskcontroller.domain.values import (
    Binding,
    CapabilityRequirement,
    EnvironmentRequirement,
    NodeState,
    RoutingPref,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.ports import FakeExecutionAdapter
from taskcontroller.execution.registry import build_registry
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore


_NOW = "2026-08-14T10:00:00Z"
_EXPIRES = "2026-08-14T11:00:00Z"
_RUN = "run.safety-a"
_NODE = "node.safety-a"
_EXEC = "exec.safety-a"
_ATTEMPT = "attempt.safety-a"
_FENCE = "fence.safety-a"
_PROV = "provider.safety-a"
_LEASE = "lease.safety-a"


def _instruction() -> bytes:
    return b"node_id: node.safety-a\nallowed_actions: [read]\ninputs: [target]\n"


def _compiler_payload(ref: str, digest: str) -> dict:
    return {
        "schema_version": "1.0",
        "artifact_type": "governed-execution-blueprint",
        "blueprint_id": "blueprint.safety-a",
        "task_id": "SCRUM-668",
        "source_bindings": {},
        "nodes": [
            {
                "action": "read",
                "node_id": "node.safety-a",
                "node_instruction_ref": ref,
                "node_instruction_digest": digest,
            }
        ],
        "topology": [{"action": "read", "terminal": True}],
        "authority_requirements": [],
    }


def _binding() -> Binding:
    return Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://safety", binding_id="validated-b1")


def _provider() -> ExecutionProviderCard:
    return ExecutionProviderCard(
        provider_id=_PROV,
        provider_kind="LOCAL",
        capability_refs=[],
        environment=None,
        bindings=[_binding()],
        trust_tier="STANDARD",
        cost_class="FREE",
    )


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        execution_id=_EXEC,
        contract_ref="contract.safety-a",
        attempt=1,
        attempt_id=_ATTEMPT,
        fencing_token=_FENCE,
        capability_requirements=CapabilityRequirement(capability_id="cap.read"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
    )


def _receipt() -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id="receipt.safety-a",
        contract_ref="contract.safety-a",
        execution_ref=ExecutionRef(
            execution_id=_EXEC,
            attempt=1,
            attempt_id=_ATTEMPT,
            fencing_token=_FENCE,
        ),
        selected_provider=ProviderRef(provider_id=_PROV),
        binding=BindingRef(binding_id="validated-b1"),
        status="ROUTING",
    )


def _fabric() -> tuple[ExecutionFabric, FakeExecutionAdapter]:
    lease = WorkLease(
        lease_id=_LEASE,
        run_id=_RUN,
        node_id=_NODE,
        execution_id=_EXEC,
        attempt_id=_ATTEMPT,
        holder=ProviderRef(provider_id=_PROV),
        fencing_token=_FENCE,
        granted_at=_NOW,
        expires_at=_EXPIRES,
        status=LeaseStatus.ACTIVE.value,
    )
    run = TeamRunState(
        run_id=_RUN,
        status=RunStatus.RUNNING.value,
        nodes={
            _NODE: NodeState(
                status=NodeStatus.RUNNING.value,
                contract_ref="contract.safety-a",
                current_attempt=1,
                lease_ref=_LEASE,
                artifact_refs=[],
            )
        },
        active_attempts=[_ATTEMPT],
        active_leases=[_LEASE],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={
            _ATTEMPT: make_attempt_record(
                attempt_id=_ATTEMPT,
                run_id=_RUN,
                node_id=_NODE,
                execution_id=_EXEC,
                fencing_token=_FENCE,
                current_attempt_number=1,
                current_lease_id=_LEASE,
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
    adapter = FakeExecutionAdapter(adapter_key="fake.safety-a")
    fabric = ExecutionFabric(
        build_registry([adapter]),
        LeaseManager(store),
    )
    return fabric, adapter


def test_node_instruction_ref_cannot_escape_root_with_dotdot(tmp_path: Path):
    outside = tmp_path / "outside.yaml"
    raw = _instruction()
    outside.write_bytes(raw)
    root = tmp_path / "root"
    root.mkdir()
    payload = _compiler_payload("../outside.yaml", "sha256:" + hashlib.sha256(raw).hexdigest())

    with pytest.raises(TaskControllerValidationError):
        compile_blueprint(payload, node_instruction_root=root)


def test_node_instruction_ref_cannot_escape_root_with_absolute_path(tmp_path: Path):
    outside = tmp_path / "outside.yaml"
    raw = _instruction()
    outside.write_bytes(raw)
    payload = _compiler_payload(str(outside), "sha256:" + hashlib.sha256(raw).hexdigest())

    with pytest.raises(TaskControllerValidationError):
        compile_blueprint(payload, node_instruction_root=tmp_path / "root")


def test_node_instruction_symlink_cannot_escape_root(tmp_path: Path):
    outside = tmp_path / "outside.yaml"
    raw = _instruction()
    outside.write_bytes(raw)
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked.yaml").symlink_to(outside)
    payload = _compiler_payload("linked.yaml", "sha256:" + hashlib.sha256(raw).hexdigest())

    with pytest.raises(TaskControllerValidationError):
        compile_blueprint(payload, node_instruction_root=root)


def test_dispatch_envelope_uses_validated_binding_id_only():
    fabric, adapter = _fabric()

    ack = fabric.dispatch(
        _request(),
        _receipt(),
        _provider(),
        _RUN,
        _NODE,
        "command.safety-a",
        now=_NOW,
        binding_id="attacker-supplied-binding",
    )

    assert ack.status == "ACCEPTED"
    assert len(adapter.dispatched) == 1
    assert adapter.dispatched[0].binding is not None
    assert adapter.dispatched[0].binding.binding_id == "validated-b1"
