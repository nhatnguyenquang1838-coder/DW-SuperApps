"""WP4 execution fabric (NO GWC).

Provider-neutral fabric between WP3 route/receipt and an explicitly injected
binding adapter. Enforces exact request/receipt/lease/fencing correlation before
dispatch, normalizes adapter acks/signals, and hands trusted signals to the WP2
EventRouter without bypassing WP2 authority.

Modules:
- errors: typed ExecutionFabricError hierarchy
- types: runtime-only DispatchEnvelope / DispatchAck / CancelAck / AdapterSignal
- ports: product-neutral ExecutionAdapter port + deterministic FakeExecutionAdapter
- registry: explicit immutable AdapterRegistry (duplicate-key fail-closed)
- fabric / dispatch: dispatch preflight + idempotent dispatch
- signals: AdapterSignal -> canonical AgentEvent -> EventRouter
"""

from __future__ import annotations

from taskcontroller.execution.errors import (
    AdapterNotFoundError,
    AdapterUnsupportedError,
    DispatchRejectedError,
    DuplicateCommandError,
    ExecutionCorrelationError,
    ExecutionFabricError,
    StaleLeaseError,
)
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.orchestrator import route_and_dispatch, signal_to_event
from taskcontroller.execution.ports import ExecutionAdapter, FakeExecutionAdapter
from taskcontroller.execution.registry import AdapterRegistry, build_registry
from taskcontroller.execution.types import (
    AdapterSignal,
    CancelAck,
    DispatchAck,
    DispatchEnvelope,
)

__all__ = [
    "ExecutionFabricError",
    "ExecutionCorrelationError",
    "AdapterNotFoundError",
    "AdapterUnsupportedError",
    "DuplicateCommandError",
    "DispatchRejectedError",
    "StaleLeaseError",
    "ExecutionAdapter",
    "FakeExecutionAdapter",
    "AdapterRegistry",
    "build_registry",
    "DispatchEnvelope",
    "DispatchAck",
    "CancelAck",
    "AdapterSignal",
    "ExecutionFabric",
    "route_and_dispatch",
    "signal_to_event",
]
