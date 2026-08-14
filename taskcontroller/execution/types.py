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


# ---------------------------------------------------------------------------
# DispatchEnvelope — runtime-only, immutable correlation bundle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchEnvelope:
    """Exact request/receipt/binding correlation + current lease identity/fencing.

    All fields are caller/adapter supplied. The fabric builds this only after
    passing the fail-closed pre-dispatch correlation checks.
    """

    command_id: str  # caller/idempotency identity for exactly-once dispatch
    request: ExecutionRequest
    receipt: ExecutionReceipt
    provider: ProviderRef
    binding: BindingRef | None
    lease_id: str
    fencing_token: str
    # adapter key / binding type that resolved the adapter
    adapter_key: str

    def canonical_fingerprint(self) -> dict[str, Any]:
        """Stable fingerprint over correlation identity (for idempotency).

        Includes the request's correlation-bearing fields so a re-dispatched
        command_id with a genuinely different envelope (contract, attempt, or
        capability requirement) is detected as a conflict rather than silently
        returning the prior ack.
        """
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
        }


# ---------------------------------------------------------------------------
# DispatchAck — normalized adapter acknowledgement (runtime-only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchAck:
    """Normalized dispatch acknowledgement from an adapter (runtime-only)."""

    command_id: str
    accepted: bool
    status: str  # "ACCEPTED" | "REJECTED" | "FAILED"
    adapter_key: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# CancelAck — normalized cancel acknowledgement (runtime-only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CancelAck:
    """Normalized cancel acknowledgement from an adapter (runtime-only)."""

    command_id: str
    accepted: bool
    status: str  # "ACCEPTED" | "REJECTED" | "UNSUPPORTED"
    adapter_key: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# AdapterSignal — normalized trusted signal carrying explicit canonical fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdapterSignal:
    """Normalized adapter signal handed to WP2 EventRouter.

    Carries explicit event_id / event_type / sequence / execution correlation /
    fencing / payload / artifact refs / idempotency key. The fabric converts
    this into a canonical AgentEvent; WP2 remains the sole acceptance authority.
    """

    event_id: str
    event_type: str  # EventType value
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
