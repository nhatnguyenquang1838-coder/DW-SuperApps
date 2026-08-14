"""WP3 deterministic routing / provider selection (NO GWC).

Pure function over explicit snapshots: registry + ExecutionRequest -> selected
provider + binding (or typed no-route). No provider/Slack/Hermes/MCP/HTTP/CLI
invocation, no WP2 runtime/lease mutation, no wall-clock/randomness.

Modules:
- errors: typed routing errors
- semver: bounded deterministic SemVer comparator (stdlib only)
- registry: immutable provider/capability snapshot + duplicate-ID semantics
- eligibility: capability / environment / locality / binding predicates
- selector: deterministic ranking + local/remote fallback selection
- receipt: compiles route result + request into an exact ExecutionReceipt
"""

from __future__ import annotations

from taskcontroller.routing.errors import (
    RoutingError,
    RoutingEligibilityError,
    RoutingNoRouteError,
    RoutingRegistrationError,
)
from taskcontroller.routing.registry import Registry, build_registry
from taskcontroller.routing.router import route
from taskcontroller.routing.semver import (
    compare_versions,
    parse_version,
    satisfies_min_version,
)

__all__ = [
    "RoutingError",
    "RoutingRegistrationError",
    "RoutingEligibilityError",
    "RoutingNoRouteError",
    "Registry",
    "build_registry",
    "route",
    "compare_versions",
    "parse_version",
    "satisfies_min_version",
]
