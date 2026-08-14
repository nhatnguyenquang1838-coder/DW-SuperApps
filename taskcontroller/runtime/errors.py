"""WP2 runtime errors (NO GWC, framework-neutral)."""

from __future__ import annotations

from taskcontroller.kernel.errors import KernelError


class RuntimeError(KernelError):
    """Base for WP2 runtime-layer errors."""


class ConcurrentStateError(RuntimeError):
    """Stale CAS write: expected_version != current state version."""


class EventRejected(RuntimeError):
    """AgentEvent rejected by acceptance gate; reason carried in `reason`."""


class LeaseConflictError(RuntimeError):
    """Lease lifecycle violation (currentness, replacement detachment, etc.)."""
