"""WP4 dispatch preflight + envelope construction (NO GWC, NO adapter call here).

Pure correlation checks between WP3 route/receipt and the live WP2 runtime lease.
All checks are fail-closed: any mismatch raises ExecutionCorrelationError and the
caller must NOT invoke the adapter. No lease is granted/renewed/released here.
"""

from __future__ import annotations

from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import ExecutionProviderCard, ExecutionReceipt, ExecutionRequest
from taskcontroller.execution.errors import ExecutionCorrelationError
from taskcontroller.execution.types import DispatchEnvelope
from taskcontroller.runtime.lease import LeaseManager


def _require(condition: bool, msg: str) -> None:
    if not condition:
        raise ExecutionCorrelationError(msg)


def check_correlation(
    request: ExecutionRequest,
    receipt: ExecutionReceipt,
    provider: ExecutionProviderCard,
    binding_id: str | None,
    lease_mgr: LeaseManager,
    run_id: str,
    node_id: str,
    now: str,
) -> str:
    """Fail-closed pre-dispatch correlation. Returns the current ACTIVE lease_id.

    Checks (contract-frozen):
    - request.contract_ref == receipt.contract_ref
    - execution_id/attempt/attempt_id/fencing exact between request and receipt
    - selected provider in receipt resolves to the routed provider
    - selected binding resolves exactly to a provider binding (when present)
    - LeaseManager.current(run,node,execution,attempt) exists and is ACTIVE
    - lease.fencing_token == request/receipt fencing
    - lease holder identity matches selected provider when a holder is present
    - stale/replaced/expired/no lease => ExecutionCorrelationError (no adapter call)
    """
    # contract correlation
    _require(
        request.contract_ref == receipt.contract_ref,
        f"contract_ref mismatch: request {request.contract_ref!r} != "
        f"receipt {receipt.contract_ref!r}",
    )
    # execution correlation (request <-> receipt)
    ref = receipt.execution_ref
    _require(
        ref.execution_id == request.execution_id,
        f"execution_id mismatch: receipt {ref.execution_id!r} != "
        f"request {request.execution_id!r}",
    )
    _require(
        ref.attempt == request.attempt,
        f"attempt mismatch: receipt {ref.attempt!r} != request {request.attempt!r}",
    )
    _require(
        ref.attempt_id == request.attempt_id,
        f"attempt_id mismatch: receipt {ref.attempt_id!r} != "
        f"request {request.attempt_id!r}",
    )
    _require(
        ref.fencing_token == request.fencing_token,
        "fencing_token mismatch between receipt and request",
    )

    # selected provider resolves to the routed provider
    _require(
        receipt.selected_provider.provider_id == provider.provider_id,
        f"selected provider {receipt.selected_provider.provider_id!r} != "
        f"routed provider {provider.provider_id!r}",
    )

    # selected binding resolves exactly to a provider binding (when present)
    if receipt.binding is not None:
        _require(
            binding_id is not None,
            "receipt carries a binding but no provider binding resolved",
        )
        _require(
            receipt.binding.binding_id == binding_id,
            f"selected binding {receipt.binding.binding_id!r} != "
            f"provider binding {binding_id!r}",
        )

    # lease currentness (WP2 authority)
    lease = lease_mgr.current(
        run_id,
        node_id,
        request.execution_id,
        request.attempt_id,
        now,
    )
    if lease is None:
        raise ExecutionCorrelationError(
            f"no current ACTIVE lease for {run_id}/{node_id}/"
            f"{request.execution_id}/{request.attempt_id}; dispatch blocked"
        )
    _require(
        lease.fencing_token == request.fencing_token,
        f"lease fencing_token {lease.fencing_token!r} != "
        f"request fencing {request.fencing_token!r}",
    )
    if lease.holder is not None:
        _require(
            lease.holder.provider_id == provider.provider_id,
            f"lease holder {lease.holder.provider_id!r} != "
            f"selected provider {provider.provider_id!r}",
        )
    return lease.lease_id


def build_envelope(
    command_id: str,
    request: ExecutionRequest,
    receipt: ExecutionReceipt,
    provider: ExecutionProviderCard,
    binding_id: str | None,
    lease_id: str,
    adapter_key: str,
) -> DispatchEnvelope:
    """Construct the immutable runtime-only DispatchEnvelope after preflight."""
    return DispatchEnvelope(
        command_id=command_id,
        request=request,
        receipt=receipt,
        provider=ProviderRef(provider_id=provider.provider_id),
        binding=BindingRef(binding_id=binding_id) if binding_id else None,
        lease_id=lease_id,
        fencing_token=request.fencing_token,
        adapter_key=adapter_key,
    )
