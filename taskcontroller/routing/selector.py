"""WP3 deterministic selector (NO GWC, pure function over snapshots).

Selects exactly one (provider, binding) for a request or raises a typed
RoutingNoRouteError with a deterministic reason. Never picks an arbitrary
fallback.

Ranking among eligible candidates (documented, deterministic):
1. preferred_kinds order first (ranking, not eligibility expansion)
2. lower cost: FREE < LOW < MEDIUM < HIGH
3. higher trust: TRUSTED > STANDARD > SANDBOX > UNVERIFIED
4. final tie-break: provider_id lexical

Missing optional cost/trust ranks AFTER declared values, never better than
explicit trusted/free metadata.

Locality fallback:
- ANY imposes no locality filter.
- LOCAL accepts LOCAL-kind or env-metadata LOCAL.
- REMOTE requires explicit non-local classification.
- If a LOCAL-first selection yields no candidate AND remote_fallback=True,
  a second REMOTE/ANY candidate pass is allowed; otherwise fail closed.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.enums import CostClass, ProviderKind, TrustTier
from taskcontroller.domain.models import ExecutionProviderCard, ExecutionRequest
from taskcontroller.domain.values import Binding, RoutingPref
from taskcontroller.routing.eligibility import (
    eligible_bindings,
    provider_eligibility,
)
from taskcontroller.routing.errors import RoutingNoRouteError
from taskcontroller.routing.registry import Registry

# lower rank = preferred
_COST_RANK = {
    CostClass.FREE.value: 0,
    CostClass.LOW.value: 1,
    CostClass.MEDIUM.value: 2,
    CostClass.HIGH.value: 3,
}
_TRUST_RANK = {
    TrustTier.TRUSTED.value: 0,
    TrustTier.STANDARD.value: 1,
    TrustTier.SANDBOX.value: 2,
    TrustTier.UNVERIFIED.value: 3,
}
# missing optional metadata ranks AFTER declared values
_MISSING_COST_RANK = 4
_MISSING_TRUST_RANK = 4


def _cost_rank(value: str | None) -> int:
    if value is None:
        return _MISSING_COST_RANK
    return _COST_RANK.get(value, _MISSING_COST_RANK)


def _trust_rank(value: str | None) -> int:
    if value is None:
        return _MISSING_TRUST_RANK
    return _TRUST_RANK.get(value, _MISSING_TRUST_RANK)


def _preferred_kind_rank(provider: ExecutionProviderCard, preferred: list[str]) -> int:
    """0 if provider kind is first preferred, else index+1; len(preferred) if absent."""
    if not preferred:
        return 0
    try:
        return preferred.index(provider.provider_kind)
    except ValueError:
        return len(preferred)


def _rank_key(
    provider: ExecutionProviderCard, preferred: list[str]
) -> tuple[int, int, int, str]:
    return (
        _preferred_kind_rank(provider, preferred),
        _cost_rank(provider.cost_class),
        _trust_rank(provider.trust_tier),
        provider.provider_id,
    )


def _eligible_provider_binding_pairs(
    registry: Registry, request: ExecutionRequest
) -> list[tuple[ExecutionProviderCard, Binding]]:
    """All (provider, binding) pairs that pass eligibility, deterministically ordered."""
    pairs: list[tuple[ExecutionProviderCard, Binding]] = []
    cap_id = request.capability_requirements.capability_id
    cap_card = registry.get_capability(cap_id)
    # iterate providers in deterministic (sorted) order for stable ranking seed
    for pid in registry.provider_ids():
        provider = registry.get_provider(pid)
        assert provider is not None
        reason = provider_eligibility(provider, request, registry)
        if reason is not None:
            continue
        if cap_card is None:
            continue
        bindings = eligible_bindings(provider, cap_card)
        if not bindings:
            continue
        # pick first eligible binding per provider (already deterministically sorted)
        pairs.append((provider, bindings[0]))
    return pairs


def _rank_pairs(
    pairs: list[tuple[ExecutionProviderCard, Binding]],
    request: ExecutionRequest,
) -> list[tuple[ExecutionProviderCard, Binding]]:
    preferred = list(request.routing_preferences.preferred_kinds)
    # stable sort by documented ranking key => deterministic
    return sorted(pairs, key=lambda pb: _rank_key(pb[0], preferred))


def select(
    registry: Registry, request: ExecutionRequest
) -> tuple[ExecutionProviderCard, Binding]:
    """Select exactly one (provider, binding) or raise RoutingNoRouteError.

    Pure function over (registry, request). No network/clock/random.
    """
    pref = request.routing_preferences
    cap_id = request.capability_requirements.capability_id
    cap_card = registry.get_capability(cap_id)
    if cap_card is None:
        raise RoutingNoRouteError(f"capability_id {cap_id!r} not registered")

    pairs = _eligible_provider_binding_pairs(registry, request)
    if pairs:
        ranked = _rank_pairs(pairs, request)
        return ranked[0]

    # locality fallback: LOCAL-first with remote_fallback=true => second REMOTE/ANY pass
    from taskcontroller.domain.enums import Locality

    if Locality(pref.locality) == Locality.LOCAL and pref.remote_fallback:
        fallback_req = ExecutionRequest(
            execution_id=request.execution_id,
            contract_ref=request.contract_ref,
            attempt=request.attempt,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            capability_requirements=request.capability_requirements,
            environment_requirements=request.environment_requirements,
            routing_preferences=RoutingPref(
                locality=Locality.ANY.value, remote_fallback=False
            ),
            inputs=request.inputs,
            permissions=request.permissions,
            expected_outputs=request.expected_outputs,
            retry=request.retry,
            plan_version=request.plan_version,
            run_version=request.run_version,
        )
        fb_pairs = _eligible_provider_binding_pairs(registry, fallback_req)
        if fb_pairs:
            ranked = _rank_pairs(_rank_pairs(fb_pairs, request), request)
            return ranked[0]

    raise RoutingNoRouteError(
        f"no eligible provider/binding for capability {cap_id!r} "
        f"(locality={pref.locality}, remote_fallback={pref.remote_fallback})"
    )
