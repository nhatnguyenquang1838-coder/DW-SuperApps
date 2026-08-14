"""WP3 top-level router entrypoint (NO GWC, NO dispatch).

Pure orchestration over explicit snapshots: a Registry + an ExecutionRequest +
caller-supplied receipt identity/time map to exactly one ExecutionReceipt, or a
typed RoutingNoRouteError. No provider/Slack/Hermes/MCP/HTTP/CLI invocation, no
WP2 runtime/lease mutation, no wall-clock/randomness.
"""

from __future__ import annotations

from taskcontroller.domain.models import ExecutionProviderCard, ExecutionRequest
from taskcontroller.domain.values import Binding
from taskcontroller.routing.eligibility import eligible_bindings
from taskcontroller.routing.errors import RoutingNoRouteError
from taskcontroller.routing.receipt import compile_receipt
from taskcontroller.routing.registry import Registry
from taskcontroller.routing.selector import select


def route(
    registry: Registry,
    request: ExecutionRequest,
    receipt_id: str,
    accepted_at: str | None = None,
) -> "object":
    """Select a provider+binding and compile the exact ExecutionReceipt.

    Pure function. The router does not generate identity/time: the caller
    supplies ``receipt_id`` and explicit ``accepted_at`` (or None).
    """
    provider, binding = select(registry, request)
    return compile_receipt(request, provider, binding, receipt_id, accepted_at)
