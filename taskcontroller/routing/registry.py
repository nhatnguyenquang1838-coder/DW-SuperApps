"""WP3 provider/capability registry (immutable snapshot, NO GWC).

A Registry is built once from explicit provider/capability lists and provides
read-only lookup. Identity is preserved by provider_id / capability_id:

- duplicate provider_id with a NON-IDENTICAL card => RoutingRegistrationError (fail closed)
- identical re-registration (same id, equal card) => idempotent (no-op)
- duplicate capability_id with non-identical card => RoutingRegistrationError
- identical capability re-registration => idempotent

No network/random/time discovery. Pure function over explicit snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from taskcontroller.domain.models import CapabilityCard, ExecutionProviderCard
from taskcontroller.routing.errors import RoutingRegistrationError


@dataclass(frozen=True)
class Registry:
    """Immutable registry snapshot of providers + capabilities keyed by id."""

    providers: dict[str, ExecutionProviderCard] = field(default_factory=dict)
    capabilities: dict[str, CapabilityCard] = field(default_factory=dict)

    def get_provider(self, provider_id: str) -> ExecutionProviderCard | None:
        return self.providers.get(provider_id)

    def get_capability(self, capability_id: str) -> CapabilityCard | None:
        return self.capabilities.get(capability_id)

    def provider_ids(self) -> list[str]:
        # deterministic order for stable iteration/tests
        return sorted(self.providers.keys())

    def capability_ids(self) -> list[str]:
        return sorted(self.capabilities.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "capabilities": {k: v.to_dict() for k, v in self.capabilities.items()},
        }


def _card_equal(a: Any, b: Any) -> bool:
    return a.to_dict() == b.to_dict()


def build_registry(
    providers: list[ExecutionProviderCard],
    capabilities: list[CapabilityCard],
) -> Registry:
    """Build an immutable Registry, enforcing duplicate-ID semantics."""
    prov: dict[str, ExecutionProviderCard] = {}
    for p in providers:
        existing = prov.get(p.provider_id)
        if existing is not None:
            if not _card_equal(existing, p):
                raise RoutingRegistrationError(
                    f"duplicate provider_id {p.provider_id!r} with non-identical card"
                )
            # identical => idempotent no-op
            continue
        prov[p.provider_id] = p

    caps: dict[str, CapabilityCard] = {}
    for c in capabilities:
        existing = caps.get(c.capability_id)
        if existing is not None:
            if not _card_equal(existing, c):
                raise RoutingRegistrationError(
                    f"duplicate capability_id {c.capability_id!r} with non-identical card"
                )
            continue
        caps[c.capability_id] = c

    return Registry(providers=prov, capabilities=caps)
