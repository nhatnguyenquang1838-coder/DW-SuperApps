"""WP3 routing errors (NO GWC, framework-neutral)."""

from __future__ import annotations

from taskcontroller.errors import TaskControllerValidationError


class RoutingError(TaskControllerValidationError):
    """Base for WP3 routing-layer errors."""


class RoutingRegistrationError(RoutingError):
    """Provider/capability registry mutation rejected (duplicate non-identical ID, etc.)."""


class RoutingEligibilityError(RoutingError):
    """A provider/capability failed an eligibility constraint (deterministic reason)."""


class RoutingNoRouteError(RoutingError):
    """No eligible provider/binding for the request (typed, deterministic reason)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"no eligible route: {reason}")
        self.reason = reason
