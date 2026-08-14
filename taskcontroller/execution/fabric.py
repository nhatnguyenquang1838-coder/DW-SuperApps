"""WP4 execution fabric orchestrator (NO GWC, NO lease/state mutation).

Bridges WP3 route/receipt and an explicitly injected adapter. Dispatch is a pure
coordination step: it validates correlation (via dispatch.check_correlation),
enforces exactly-once within a fabric snapshot (command_id idempotency), invokes
the adapter exactly once, and returns a normalized DispatchAck. It never grants/
renews/releases/revokes leases and never mutates VersionedRunState itself.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.models import ExecutionProviderCard, ExecutionReceipt, ExecutionRequest
from taskcontroller.execution.dispatch import build_envelope, check_correlation
from taskcontroller.execution.errors import (
    AdapterNotFoundError,
    DispatchRejectedError,
    DuplicateCommandError,
)
from taskcontroller.execution.ports import DispatchAck, ExecutionAdapter
from taskcontroller.execution.registry import AdapterRegistry
from taskcontroller.execution.types import DispatchEnvelope
from taskcontroller.runtime.lease import LeaseManager


def _resolve_adapter(
    registry: AdapterRegistry, adapter_key: str | None, binding_type: str
) -> ExecutionAdapter:
    if adapter_key is not None:
        return registry.lookup_by_key(adapter_key)
    return registry.lookup_by_binding_type(binding_type)


class ExecutionFabric:
    """See module docstring; pure coordination over injected registry/lease."""

    def __init__(self, registry: AdapterRegistry, lease_mgr: LeaseManager) -> None:
        self._registry = registry
        self._lease_mgr = lease_mgr
        # command_id -> (fingerprint, ack) within this fabric snapshot
        self._dispatched: dict[str, tuple[dict[str, Any], DispatchAck]] = {}

    def dispatch(
        self,
        request: ExecutionRequest,
        receipt: ExecutionReceipt,
        provider: ExecutionProviderCard,
        run_id: str,
        node_id: str,
        command_id: str,
        now: str,
        binding_id: str | None = None,
        adapter_key: str | None = None,
    ) -> DispatchAck:
        """Preflight-correlate then invoke the adapter exactly once.

        ``now`` is an explicit caller-supplied ISO timestamp used for lease
        currentness/expiry. Idempotency: re-dispatch with the same command_id +
        identical canonical envelope returns the prior ack and does NOT call the
        adapter again. Same command_id with a different envelope =>
        DuplicateCommand.
        """
        # Resolve the binding_id from the provider's bindings that matches the
        # receipt's selected binding (the receipt binding must resolve to a real
        # provider binding). Pass None when the receipt carries no binding.
        resolved_binding_id: str | None = None
        if receipt.binding is not None:
            match = next(
                (b.binding_id for b in provider.bindings if b.binding_id == receipt.binding.binding_id),
                None,
            )
            resolved_binding_id = match
        binding_type = (
            provider.bindings[0].kind if provider.bindings else ""
        )
        adapter = _resolve_adapter(self._registry, adapter_key, binding_type)

        # fail-closed preflight (may raise ExecutionCorrelationError; no adapter call)
        lease_id = check_correlation(
            request, receipt, provider, resolved_binding_id, self._lease_mgr,
            run_id, node_id, now,
        )

        envelope = build_envelope(
            command_id, request, receipt, provider, binding_id, lease_id,
            getattr(adapter, "adapter_key", adapter_key or ""),
        )

        fp = envelope.canonical_fingerprint()
        prior = self._dispatched.get(command_id)
        if prior is not None:
            prior_fp, prior_ack = prior
            if prior_fp == fp:
                # identical command => no second adapter call
                return prior_ack
            raise DuplicateCommandError(
                f"command_id {command_id!r} reused with a different "
                f"canonical envelope"
            )

        ack = adapter.dispatch(envelope)
        if ack.status == "REJECTED":
            raise DispatchRejectedError(
                ack.detail or f"adapter rejected command {command_id!r}"
            )
        self._dispatched[command_id] = (fp, ack)
        return ack
