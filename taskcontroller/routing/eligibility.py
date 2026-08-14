"""WP3 eligibility evaluation (pure, deterministic, NO GWC).

Each eligibility predicate consumes explicit snapshots (registry + request) and
returns either ``None`` (eligible) or a deterministic reason string (ineligible).
No wall-clock, randomness, network, or env discovery.
"""

from __future__ import annotations

from taskcontroller.domain.enums import Locality, ProviderKind
from taskcontroller.domain.models import (
    CapabilityCard,
    ExecutionProviderCard,
    ExecutionRequest,
)
from taskcontroller.domain.values import (
    CapabilityRequirement,
    EnvironmentRequirement,
    RoutingPref,
)
from taskcontroller.routing.registry import Registry
from taskcontroller.routing.semver import satisfies_min_version


# ---------------------------------------------------------------------------
# capability eligibility
# ---------------------------------------------------------------------------

def check_capability(
    provider: ExecutionProviderCard,
    requirement: CapabilityRequirement,
    registry: Registry,
) -> str | None:
    """Return reason (str) if ineligible, else None.

    - requested capability_id MUST appear in provider.capability_refs
    - it MUST resolve to a registered CapabilityCard of that id
    - if requirement.min_version present: provider capability version >= min (semver)
    - idempotency / cost_class requirements are constraints, not widenings
    """
    cap_id = requirement.capability_id
    ref = next(
        (r for r in provider.capability_refs if r.capability_id == cap_id), None
    )
    if ref is None:
        return f"provider {provider.provider_id} lacks capability_ref {cap_id!r}"
    card = registry.get_capability(cap_id)
    if card is None:
        return f"capability_id {cap_id!r} not registered in registry"

    if requirement.min_version is not None:
        try:
            ok = satisfies_min_version(card.version, requirement.min_version)
        except Exception as exc:  # malformed semver => fail closed
            return f"capability {cap_id!r} version compare failed: {exc}"
        if not ok:
            return (
                f"capability {cap_id!r} version {card.version!r} "
                f"< required min_version {requirement.min_version!r}"
            )

    if requirement.idempotency is not None and requirement.idempotency != card.idempotency:
        return (
            f"capability {cap_id!r} idempotency {card.idempotency!r} "
            f"!= required {requirement.idempotency!r}"
        )
    if requirement.cost_class is not None and requirement.cost_class != card.cost_class:
        return (
            f"capability {cap_id!r} cost_class {card.cost_class!r} "
            f"!= required {requirement.cost_class!r}"
        )
    return None


# ---------------------------------------------------------------------------
# environment eligibility
# ---------------------------------------------------------------------------

def check_environment(
    provider: ExecutionProviderCard,
    requirement: EnvironmentRequirement,
) -> str | None:
    """Return reason if ineligible, else None.

    - each non-empty requested os/runtime/arch must equal provider env value
    - required capability strings must be a subset of provider env capabilities
    - if min_memory_mb > 0: provider.env.metadata.memory_mb (int) >= requirement
      (absent/invalid => ineligible)
    """
    env = provider.environment

    # Only constrain when the request actually demands environment characteristics.
    # A provider with no env metadata is eligible for an env-agnostic request.
    requires_env = (
        bool(requirement.os)
        or bool(requirement.runtime)
        or bool(requirement.arch)
        or bool(requirement.capabilities)
        or bool(requirement.min_memory_mb and requirement.min_memory_mb > 0)
    )
    if env is None:
        if requires_env:
            return (
                f"provider {provider.provider_id} has no environment "
                f"but request requires environment characteristics"
            )
        return None

    for attr in ("os", "runtime", "arch"):
        req_val = getattr(requirement, attr)
        if req_val:  # non-empty requested value must equal provider value
            prov_val = getattr(env, attr)
            if prov_val != req_val:
                return (
                    f"environment {attr} mismatch: provider {prov_val!r} "
                    f"!= required {req_val!r}"
                )

    if requirement.capabilities:
        prov_caps = set(env.capabilities or [])
        missing = [c for c in requirement.capabilities if c not in prov_caps]
        if missing:
            return (
                f"provider environment missing required capabilities: {missing!r}"
            )

    if requirement.min_memory_mb and requirement.min_memory_mb > 0:
        meta = env.metadata or {}
        mem = meta.get("memory_mb")
        if not isinstance(mem, int):
            return (
                f"provider {provider.provider_id} environment.metadata.memory_mb "
                f"absent/invalid (required {requirement.min_memory_mb}MB)"
            )
        if mem < requirement.min_memory_mb:
            return (
                f"provider memory {mem}MB < required {requirement.min_memory_mb}MB"
            )
    return None


# ---------------------------------------------------------------------------
# locality eligibility
# ---------------------------------------------------------------------------

def check_locality(provider: ExecutionProviderCard, pref: RoutingPref) -> str | None:
    """Return reason if ineligible, else None.

    - ANY: no locality filter
    - LOCAL: provider kind LOCAL OR env.metadata.locality == LOCAL
    - REMOTE: explicit non-local classification (kind != LOCAL and metadata.locality != LOCAL)
    """
    locality = Locality(pref.locality)
    if locality == Locality.ANY:
        return None

    env = provider.environment
    env_locality = (env.metadata or {}).get("locality") if env is not None else None

    is_local_kind = ProviderKind(provider.provider_kind) == ProviderKind.LOCAL
    is_local_meta = env_locality == Locality.LOCAL.value

    if locality == Locality.LOCAL:
        if is_local_kind or is_local_meta:
            return None
        return (
            f"provider {provider.provider_id} not local "
            f"(kind={provider.provider_kind}, env_locality={env_locality!r})"
        )
    # REMOTE
    if is_local_kind or is_local_meta:
        return (
            f"provider {provider.provider_id} is local but REMOTE locality requested"
        )
    return None


# ---------------------------------------------------------------------------
# binding eligibility
# ---------------------------------------------------------------------------

def eligible_bindings(
    provider: ExecutionProviderCard,
    capability: CapabilityCard,
) -> list:
    """Return bindings eligible for (provider, capability), deterministically sorted.

    Provider must expose at least one binding. If the capability's
    supported_binding_types is non-empty, binding kind must be in that allowlist.
    Deterministic stable sort by (kind, binding_id-or-empty, endpoint_ref); never
    depends on hash/set iteration order.
    """
    if not provider.bindings:
        return []
    allow = capability.supported_binding_types
    candidates = [
        b for b in provider.bindings if (not allow) or (b.kind in allow)
    ]
    if not candidates:
        return []
    return sorted(
        candidates,
        key=lambda b: (b.kind, b.binding_id or "", b.endpoint_ref),
    )


# ---------------------------------------------------------------------------
# aggregate provider eligibility
# ---------------------------------------------------------------------------

def provider_eligibility(
    provider: ExecutionProviderCard,
    request: ExecutionRequest,
    registry: Registry,
) -> str | None:
    """Full eligibility: capability + environment + locality (+ has binding).

    Returns reason (str) if ineligible, else None. Does NOT rank.
    """
    cap_reason = check_capability(
        provider, request.capability_requirements, registry
    )
    if cap_reason is not None:
        return cap_reason

    env_reason = check_environment(provider, request.environment_requirements)
    if env_reason is not None:
        return env_reason

    loc_reason = check_locality(provider, request.routing_preferences)
    if loc_reason is not None:
        return loc_reason

    cap_card = registry.get_capability(request.capability_requirements.capability_id)
    if cap_card is not None and not eligible_bindings(provider, cap_card):
        return f"provider {provider.provider_id} exposes no eligible binding"

    return None
