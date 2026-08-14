"""WP4 execution-fabric errors (NO GWC, framework-neutral)."""

from __future__ import annotations

from taskcontroller.errors import TaskControllerValidationError


class ExecutionFabricError(TaskControllerValidationError):
    """Base for WP4 execution-fabric errors."""


class ExecutionCorrelationError(ExecutionFabricError):
    """Pre-dispatch correlation/lease/fencing mismatch (fail closed)."""


class AdapterNotFoundError(ExecutionFabricError):
    """No adapter registered for the requested binding type/adapter key."""


class AdapterUnsupportedError(ExecutionFabricError):
    """Adapter does not support the requested operation (e.g. cancel)."""


class DuplicateCommandError(ExecutionFabricError):
    """Same command_id used with a different canonical envelope (conflict)."""


class DispatchRejectedError(ExecutionFabricError):
    """Adapter rejected the dispatch (normalized typed error)."""


class StaleLeaseError(ExecutionFabricError):
    """Signal/dispatch rejected because the lease is stale/replaced/expired."""
