"""WP4 orchestrator: route -> receipt -> dispatch, and adapter signal -> event.

Provider-neutral glue between WP3 routing and the WP2 runtime, with NO GWC and
NO hidden time. The orchestrator:

- route_and_dispatch: pure WP3 route() to an ExecutionReceipt, then exactly-once
  dispatch via ExecutionFabric using the caller-supplied explicit ``now``. Fails
  closed if routing yields no route (RoutingNoRouteError propagates) or if the
  fabric preflight rejects (ExecutionCorrelationError propagates).
- signal_to_event: pure conversion of a normalized AdapterSignal into a canonical
  WP2 AgentEvent. WP2 EventRouter remains the SOLE acceptance authority; this
  helper only shapes the adapter's trusted signal into the canonical event shape.

No lease is granted/renewed/released/revoked here; the fabric never mutates the
WP2 VersionedRunState. All identities (command_id, event_id, sequence,
idempotency_key, timestamp) are caller/adapter supplied.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.ids import ProducerRef
from taskcontroller.domain.models import AgentEvent, ExecutionProviderCard, ExecutionReceipt, ExecutionRequest
from taskcontroller.execution.errors import ExecutionFabricError
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.ports import DispatchAck, ExecutionAdapter
from taskcontroller.execution.registry import AdapterRegistry
from taskcontroller.execution.types import AdapterSignal
from taskcontroller.routing.registry import Registry, build_registry
from taskcontroller.routing.router import route


def route_and_dispatch(
    registry: Registry,
    request: ExecutionRequest,
    receipt_id: str,
    lease_mgr: Any,
    adapter_registry: AdapterRegistry,
    run_id: str,
    node_id: str,
    now: str,
    accepted_at: str | None = None,
    command_id: str | None = None,
    adapter_key: str | None = None,
) -> tuple[ExecutionReceipt, DispatchAck]:
    """Route the request, then dispatch exactly once via the fabric.

    Pure composition: WP3 route() -> ExecutionReceipt, then ExecutionFabric
    dispatch() with the explicit ``now``. Returns (receipt, ack). Any routing or
    correlation failure propagates (fail-closed; no adapter call on failure).
    """
    receipt = route(registry, request, receipt_id, accepted_at)
    if not isinstance(receipt, ExecutionReceipt):
        raise ExecutionFabricError(
            f"route() returned {type(receipt).__name__}, expected ExecutionReceipt"
        )
    # Resolve the routed provider card from the registry for the fabric preflight.
    provider = registry.get_provider(receipt.selected_provider.provider_id)
    if not isinstance(provider, ExecutionProviderCard):
        raise ExecutionFabricError(
            f"routed provider {receipt.selected_provider.provider_id!r} not found in registry"
        )
    fabric = ExecutionFabric(adapter_registry, lease_mgr)
    cid = command_id or receipt.receipt_id
    ack = fabric.dispatch(
        request, receipt, provider, run_id, node_id, cid, now, adapter_key=adapter_key
    )
    return receipt, ack


def signal_to_event(signal: AdapterSignal) -> AgentEvent:
    """Convert a normalized AdapterSignal into a canonical WP2 AgentEvent.

    Pure mapping only. WP2 EventRouter is the sole acceptance authority and
    performs correlation/fencing/sequence validation on the returned event.
    """
    return AgentEvent(
        event_id=signal.event_id,
        run_id=signal.run_id,
        node_id=signal.node_id,
        execution_id=signal.execution_ref.execution_id,
        attempt_id=signal.execution_ref.attempt_id,
        fencing_token=signal.fencing_token,
        sequence=signal.sequence,
        event_type=signal.event_type,
        producer=ProducerRef(producer_id=signal.provider_id),
        timestamp=signal.timestamp if signal.timestamp is not None else "",
        idempotency_key=signal.idempotency_key,
        payload=signal.payload,
        artifact_refs=signal.artifact_refs,
    )


def forward_signal_to_router(signal: AdapterSignal, router: Any, store: Any) -> Any:
    """Convert a trusted AdapterSignal and hand it to WP2 EventRouter.

    WP2 remains the SOLE acceptance authority: it performs correlation/fencing/
    sequence validation and applies explicit reducer semantics. The orchestrator
    never mutates run/node state itself for cancellation/completion signals.
    """
    event = signal_to_event(signal)
    current = store.get_run(event.run_id)
    return router.route(event, current, current.version)
