"""WP3 S2 focused tests: deterministic selector (NO GWC).

Required adversarial tests:
- shuffled provider input => same result (input-order invariance)
- equal candidates => lexical provider_id tie-break
- preferred kind wins
- free vs metered ordering
- trust ordering
- no eligible provider => typed RoutingNoRouteError
- unsupported binding => ineligible
- malformed required semver => fails closed
"""

from __future__ import annotations

import random

import pytest

from taskcontroller.domain.enums import (
    BindingType,
    CostClass,
    Idempotency,
    Locality,
    ProviderKind,
    TrustTier,
)
from taskcontroller.domain.ids import CapabilityRef
from taskcontroller.domain.models import (
    CapabilityCard,
    ExecutionProviderCard,
    ExecutionRequest,
)
from taskcontroller.domain.values import (
    Binding,
    CapabilityRequirement,
    EnvironmentInfo,
    EnvironmentRequirement,
    RoutingPref,
)
from taskcontroller.routing.errors import RoutingEligibilityError, RoutingNoRouteError
from taskcontroller.routing.registry import build_registry
from taskcontroller.routing.selector import select


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cap(version="1.0.0", binding_types=None):
    return CapabilityCard(
        capability_id="cap.gen",
        name="gen",
        version=version,
        idempotency=Idempotency.IDEMPOTENT.value,
        cost_class=CostClass.FREE.value,
        required_environment=EnvironmentRequirement(),
        supported_binding_types=binding_types or [BindingType.LOCAL_IPC.value],
    )


def _prov(pid, kind=ProviderKind.LOCAL.value, cost=CostClass.FREE.value,
          trust=TrustTier.STANDARD.value, env=None, bindings=None,
          caps=("cap.gen",)):
    return ExecutionProviderCard(
        provider_id=pid,
        provider_kind=kind,
        capability_refs=[CapabilityRef(c) for c in caps],
        environment=env,
        bindings=bindings or [Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="e", binding_id=f"{pid}.b")],
        trust_tier=trust,
        cost_class=cost,
    )


def _req(min_version=None, locality=Locality.ANY.value, remote_fallback=True,
         preferred_kinds=None):
    return ExecutionRequest(
        execution_id="exec.1",
        contract_ref="tc.1",
        attempt=1,
        attempt_id="att.1",
        fencing_token="ft-1",
        capability_requirements=CapabilityRequirement(capability_id="cap.gen", min_version=min_version),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(
            locality=locality, remote_fallback=remote_fallback,
            preferred_kinds=preferred_kinds or [],
        ),
    )


# ---------------------------------------------------------------------------
# selection happy path + determinism
# ---------------------------------------------------------------------------

class TestSelectorDeterminism:
    def test_shuffled_input_invariance(self):
        caps = [_cap()]
        providers = [
            _prov("prov.z"),
            _prov("prov.a"),
            _prov("prov.m"),
            _prov("prov.k"),
        ]
        reg_ordered = build_registry(list(providers), caps)
        reg_shuffled = build_registry(list(reversed(providers)), caps)
        sel_o = select(reg_ordered, _req())
        sel_s = select(reg_shuffled, _req())
        assert sel_o[0].provider_id == sel_s[0].provider_id

    def test_equal_candidates_lexical_tie(self):
        reg = build_registry([_prov("prov.b"), _prov("prov.a")], [_cap()])
        sel = select(reg, _req())
        assert sel[0].provider_id == "prov.a"

    def test_preferred_kind_wins(self):
        reg = build_registry(
            [
                _prov("prov.local", kind=ProviderKind.LOCAL.value),
                _prov("prov.svc", kind=ProviderKind.SERVICE.value),
            ],
            [_cap()],
        )
        sel = select(reg, _req(preferred_kinds=[ProviderKind.SERVICE.value]))
        assert sel[0].provider_id == "prov.svc"

    def test_free_before_metered(self):
        reg = build_registry(
            [_prov("prov.high", cost=CostClass.HIGH.value),
             _prov("prov.free", cost=CostClass.FREE.value)],
            [_cap()],
        )
        sel = select(reg, _req())
        assert sel[0].provider_id == "prov.free"

    def test_trust_ordering(self):
        reg = build_registry(
            [_prov("prov.unv", trust=TrustTier.UNVERIFIED.value),
             _prov("prov.trusted", trust=TrustTier.TRUSTED.value)],
            [_cap()],
        )
        sel = select(reg, _req())
        assert sel[0].provider_id == "prov.trusted"

    def test_missing_cost_ranks_after_explicit_free(self):
        reg = build_registry(
            [_prov("prov.none", cost=None),
             _prov("prov.free", cost=CostClass.FREE.value)],
            [_cap()],
        )
        sel = select(reg, _req())
        assert sel[0].provider_id == "prov.free"


# ---------------------------------------------------------------------------
# negative / fail-closed
# ---------------------------------------------------------------------------

class TestSelectorNoRoute:
    def test_no_eligible_provider(self):
        reg = build_registry([_prov("prov.1", caps=("cap.other",))], [_cap()])
        with pytest.raises(RoutingNoRouteError):
            select(reg, _req())

    def test_unsupported_binding_ineligible(self):
        # capability allows only LOCAL_IPC; provider only has CHAT => no eligible binding
        cap = _cap(binding_types=[BindingType.LOCAL_IPC.value])
        prov = _prov("prov.1", bindings=[Binding(kind=BindingType.CHAT.value, endpoint_ref="e", binding_id="b1")])
        reg = build_registry([prov], [cap])
        with pytest.raises(RoutingNoRouteError):
            select(reg, _req())

    def test_malformed_required_semver_fails_closed(self):
        reg = build_registry([_prov("prov.1")], [_cap(version="1.0.0")])
        with pytest.raises(RoutingNoRouteError):
            select(reg, _req(min_version="v2"))


# ---------------------------------------------------------------------------
# locality fallback
# ---------------------------------------------------------------------------

class TestSelectorLocalityFallback:
    def test_local_no_candidate_remote_fallback_succeeds(self):
        # only a REMOTE (service) provider exists; LOCAL pref + remote_fallback => second pass
        reg = build_registry(
            [_prov("prov.remote", kind=ProviderKind.SERVICE.value)],
            [_cap()],
        )
        sel = select(reg, _req(locality=Locality.LOCAL.value, remote_fallback=True))
        assert sel[0].provider_id == "prov.remote"

    def test_local_no_candidate_no_fallback_fails_closed(self):
        reg = build_registry(
            [_prov("prov.remote", kind=ProviderKind.SERVICE.value)],
            [_cap()],
        )
        with pytest.raises(RoutingNoRouteError):
            select(reg, _req(locality=Locality.LOCAL.value, remote_fallback=False))

    def test_remote_locality_rejects_local_only(self):
        reg = build_registry([_prov("prov.local", kind=ProviderKind.LOCAL.value)], [_cap()])
        with pytest.raises(RoutingNoRouteError):
            select(reg, _req(locality=Locality.REMOTE.value))
