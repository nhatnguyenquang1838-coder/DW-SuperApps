"""WP4 execution-fabric runtime-only value types (NO GWC, NO new WP0 schema).

All types here are runtime-only sidecars used by the fabric + adapters. They do
NOT introduce canonical WP0 domain schemas. Identities (command_id, event_id,
sequence, fencing_token, timestamps) are always caller/adapter supplied — the
fabric never generates wall-clock/random values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import ExecutionReceipt, ExecutionRequest


@dataclass(frozen=True)
class DispatchEnvelope:
    """Exact dispatch correlation plus a bounded current-step context."""

    command_id: str
    request: ExecutionRequest
    receipt: ExecutionReceipt
    provider: ProviderRef
    binding: BindingRef | None
    lease_id: str
    fencing_token: str
    adapter_key: str
    # Full RuntimePlan and conversation history are deliberately excluded.
    context: Any | None = None

    def canonical_fingerprint(self) -> dict[str, Any]:
        cap = self.request.capability_requirements
        return {
            "command_id": self.command_id,
            "execution_id": self.request.execution_id,
            "attempt": self.request.attempt,
            "attempt_id": self.request.attempt_id,
            "contract_ref": self.request.contract_ref,
            "capability_id": cap.capability_id if cap is not None else None,
            "fencing_token": self.fencing_token,
            "lease_id": self.lease_id,
            "provider_id": self.provider.provider_id,
            "binding_id": self.binding.binding_id if self.binding else None,
            "adapter_key": self.adapter_key,
            "context": self.context.to_dict() if self.context is not None else None,
        }


@dataclass(frozen=True)
class DispatchAck:
    command_id: str
    accepted: bool
    status: str
    adapter_key: str
    detail: str | None = None


@dataclass(frozen=True)
class CancelAck:
    command_id: str
    accepted: bool
    status: str
    adapter_key: str
    detail: str | None = None


@dataclass(frozen=True)
class AdapterSignal:
    event_id: str
    event_type: str
    sequence: int
    execution_ref: ExecutionRef
    node_id: str
    run_id: str
    fencing_token: str
    provider_id: str
    binding_id: str | None = None
    idempotency_key: str | None = None
    timestamp: str | None = None
    payload: dict | None = None
    artifact_refs: list[Any] = field(default_factory=list)
