"""WP3 ExecutionReceipt compiler (NO GWC, NO dispatch).

Compiles a route result (selected provider + binding) and the original
ExecutionRequest into an exact ExecutionReceipt. It does NOT invoke any provider,
Slack, Hermes, MCP, HTTP, CLI, subprocess, and does NOT mutate WP2 runtime/lease
state.

The Router does not generate identity/time: the caller supplies ``receipt_id`` and
explicit ``accepted_at`` (or None). The receipt MUST preserve exact correlation:
- contract_ref (from request)
- execution_ref (execution_id / attempt / attempt_id / fencing_token)
- selected_provider (ProviderRef from provider_id)
- binding (BindingRef from chosen binding's binding_id)

Schema validity: the compiled receipt round-trips through the canonical
ExecutionReceipt.from_dict/to_dict unchanged.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.enums import ExecutionStatus
from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import ExecutionProviderCard, ExecutionReceipt, ExecutionRequest
from taskcontroller.domain.values import Binding
from taskcontroller.routing.errors import RoutingError


def compile_receipt(
    request: ExecutionRequest,
    provider: ExecutionProviderCard,
    binding: Binding,
    receipt_id: str,
    accepted_at: str | None = None,
) -> ExecutionReceipt:
    """Compile an exact ExecutionReceipt from a route result.

    Pure function. Raises RoutingError on a correlation mismatch between the
    route result and the request (defensive: should never happen for a result
    produced by the same request).
    """
    if not isinstance(provider, ExecutionProviderCard):
        raise RoutingError("compile_receipt requires an ExecutionProviderCard")
    if not isinstance(binding, Binding):
        raise RoutingError("compile_receipt requires a Binding")

    execution_ref = ExecutionRef(
        execution_id=request.execution_id,
        attempt=request.attempt,
        attempt_id=request.attempt_id,
        fencing_token=request.fencing_token,
    )

    receipt = ExecutionReceipt(
        receipt_id=receipt_id,
        contract_ref=request.contract_ref,
        execution_ref=execution_ref,
        selected_provider=ProviderRef(provider_id=provider.provider_id),
        binding=BindingRef(binding_id=binding.binding_id) if binding.binding_id else None,
        status=ExecutionStatus.ROUTING.value,
        accepted_at=accepted_at,
    )
    return receipt


def compile_receipt_from_dicts(
    request_dict: dict[str, Any],
    provider_dict: dict[str, Any],
    binding_dict: dict[str, Any],
    receipt_id: str,
    accepted_at: str | None = None,
) -> ExecutionReceipt:
    """Convenience: compile from raw dicts (caller-side serialization)."""
    request = ExecutionRequest.from_dict(request_dict)
    provider = ExecutionProviderCard.from_dict(provider_dict)
    binding = Binding.from_dict(binding_dict)
    return compile_receipt(request, provider, binding, receipt_id, accepted_at)
