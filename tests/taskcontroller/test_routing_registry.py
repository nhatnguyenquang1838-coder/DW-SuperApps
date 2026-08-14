"""WP3 S1 focused tests: registry + eligibility (NO GWC).

Covers: duplicate-ID semantics, deterministic SemVer, capability/environment/
locality/binding eligibility, all deterministic.
"""

from __future__ import annotations

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
from taskcontroller.routing.eligibility import (
    check_capability,
    check_environment,
    check_locality,
    eligible_bindings,
    provider_eligibility,
)
from taskcontroller.routing.errors import RoutingEligibilityError, RoutingRegistrationError
from taskcontroller.routing.registry import Registry, build_registry
from taskcontroller.routing.semver import compare_versions, satisfies_min_version


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _capability(cap_id="cap.gen", version="1.2.0", idem=Idempotency.IDEMPOTENT.value,
                cost=CostClass.FREE.value, req_env=None, binding_types=None):
    return CapabilityCard(
        capability_id=cap_id,
        name="gen",
        version=version,
        idempotency=idem,
        cost_class=cost,
        required_environment=req_env or EnvironmentRequirement(),
        supported_binding_types=binding_types or [],
    )


def _provider(pid="prov.1", kind=ProviderKind.LOCAL.value, caps=("cap.gen",),
              env=None, bindings=None, trust=TrustTier.STANDARD.value,
              cost=CostClass.FREE.value):
    return ExecutionProviderCard(
        provider_id=pid,
        provider_kind=kind,
        capability_refs=[CapabilityRef(c) for c in caps],
        environment=env,
        bindings=bindings or [],
        trust_tier=trust,
        cost_class=cost,
    )


def _request(cap_id="cap.gen", min_version=None, env_req=None, pref=None):
    return ExecutionRequest(
        execution_id="exec.1",
        contract_ref="tc.1",
        attempt=1,
        attempt_id="att.1",
        fencing_token="ft-1",
        capability_requirements=CapabilityRequirement(capability_id=cap_id, min_version=min_version),
        environment_requirements=env_req or EnvironmentRequirement(),
        routing_preferences=pref or RoutingPref(),
    )


# ---------------------------------------------------------------------------
# SemVer
# ---------------------------------------------------------------------------

class TestSemVer:
    def test_numeric_order(self):
        assert compare_versions("1.0.0", "2.0.0") == -1
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("1.2.0", "1.2.0") == 0
        assert compare_versions("1.2.3", "1.2.10") == -1

    def test_prerelease_lower_than_release(self):
        assert compare_versions("1.0.0-alpha", "1.0.0") == -1
        assert compare_versions("1.0.0", "1.0.0-alpha") == 1

    def test_satisfies_min(self):
        assert satisfies_min_version("1.2.0", "1.0.0") is True
        assert satisfies_min_version("1.0.0", "1.2.0") is False
        assert satisfies_min_version("1.2.0", "1.2.0") is True

    def test_malformed_fails_closed(self):
        with pytest.raises(RoutingEligibilityError):
            satisfies_min_version("not-a-version", "1.0.0")
        with pytest.raises(RoutingEligibilityError):
            satisfies_min_version("1.0.0", "v2")


# ---------------------------------------------------------------------------
# registry duplicate-ID semantics
# ---------------------------------------------------------------------------

class TestRegistryDuplicateIds:
    def test_identical_provider_reregistration_idempotent(self):
        p = _provider()
        reg = build_registry([p, p], [])
        assert len(reg.providers) == 1

    def test_nonidentical_provider_duplicate_rejected(self):
        p1 = _provider(pid="prov.1")
        p2 = _provider(pid="prov.1", kind=ProviderKind.SERVICE.value)
        with pytest.raises(RoutingRegistrationError, match="duplicate provider_id"):
            build_registry([p1, p2], [])

    def test_identical_capability_reregistration_idempotent(self):
        c = _capability()
        reg = build_registry([], [c, c])
        assert len(reg.capabilities) == 1

    def test_nonidentical_capability_duplicate_rejected(self):
        c1 = _capability(version="1.0.0")
        c2 = _capability(version="2.0.0")
        with pytest.raises(RoutingRegistrationError, match="duplicate capability_id"):
            build_registry([], [c1, c2])


# ---------------------------------------------------------------------------
# capability eligibility
# ---------------------------------------------------------------------------

class TestCapabilityEligibility:
    def test_missing_capability_ref(self):
        reg = build_registry([_provider(caps=("cap.other",))], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_capability(p, _request().capability_requirements, reg)
        assert reason is not None and "lacks capability_ref" in reason

    def test_unregistered_capability_card(self):
        reg = Registry(
            providers={"prov.1": _provider()},
            capabilities={},  # cap.gen not registered
        )
        p = reg.get_provider("prov.1")
        reason = check_capability(p, _request().capability_requirements, reg)
        assert reason is not None and "not registered" in reason

    def test_min_version_satisfied(self):
        reg = build_registry([_provider()], [_capability(version="1.2.0")])
        p = reg.get_provider("prov.1")
        reason = check_capability(
            p, _request(min_version="1.0.0").capability_requirements, reg
        )
        assert reason is None

    def test_min_version_unsatisfied(self):
        reg = build_registry([_provider()], [_capability(version="1.0.0")])
        p = reg.get_provider("prov.1")
        reason = check_capability(
            p, _request(min_version="2.0.0").capability_requirements, reg
        )
        assert reason is not None and "min_version" in reason

    def test_malformed_min_version_fails_closed(self):
        reg = build_registry([_provider()], [_capability(version="1.0.0")])
        p = reg.get_provider("prov.1")
        reason = check_capability(
            p, _request(min_version="v2").capability_requirements, reg
        )
        assert reason is not None and "version compare failed" in reason

    def test_idempotency_mismatch(self):
        reg = build_registry(
            [_provider()],
            [_capability(idem=Idempotency.IDEMPOTENT.value)],
        )
        p = reg.get_provider("prov.1")
        req = CapabilityRequirement(
            capability_id="cap.gen", idempotency=Idempotency.NON_IDEMPOTENT.value
        )
        reason = check_capability(p, req, reg)
        assert reason is not None and "idempotency" in reason


# ---------------------------------------------------------------------------
# environment eligibility
# ---------------------------------------------------------------------------

class TestEnvironmentEligibility:
    def test_os_mismatch(self):
        env = EnvironmentInfo(os="linux")
        reg = build_registry([_provider(env=env)], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_environment(
            p, EnvironmentRequirement(os="windows")
        )
        assert reason is not None and "os mismatch" in reason

    def test_capability_subset_ok(self):
        env = EnvironmentInfo(capabilities=["gpu", "tpu"])
        reg = build_registry([_provider(env=env)], [_capability()])
        p = reg.get_provider("prov.1")
        assert check_environment(p, EnvironmentRequirement(capabilities=["gpu"])) is None

    def test_capability_missing(self):
        env = EnvironmentInfo(capabilities=["gpu"])
        reg = build_registry([_provider(env=env)], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_environment(p, EnvironmentRequirement(capabilities=["tpu"]))
        assert reason is not None and "missing required capabilities" in reason

    def test_memory_satisfied(self):
        env = EnvironmentInfo(metadata={"memory_mb": 4096})
        reg = build_registry([_provider(env=env)], [_capability()])
        p = reg.get_provider("prov.1")
        assert check_environment(p, EnvironmentRequirement(min_memory_mb=2048)) is None

    def test_memory_absent_ineligible(self):
        env = EnvironmentInfo(metadata={})
        reg = build_registry([_provider(env=env)], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_environment(p, EnvironmentRequirement(min_memory_mb=2048))
        assert reason is not None and "memory_mb" in reason

    def test_no_environment_ineligible(self):
        reg = build_registry([_provider(env=None)], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_environment(p, EnvironmentRequirement(os="linux"))
        assert reason is not None and "no environment" in reason


# ---------------------------------------------------------------------------
# locality eligibility
# ---------------------------------------------------------------------------

class TestLocalityEligibility:
    def test_any_no_filter(self):
        reg = build_registry([_provider()], [_capability()])
        p = reg.get_provider("prov.1")
        assert check_locality(p, RoutingPref(locality=Locality.ANY.value)) is None

    def test_local_kind_accepted(self):
        reg = build_registry([_provider(kind=ProviderKind.LOCAL.value)], [_capability()])
        p = reg.get_provider("prov.1")
        assert check_locality(p, RoutingPref(locality=Locality.LOCAL.value)) is None

    def test_local_metadata_accepted(self):
        env = EnvironmentInfo(metadata={"locality": "LOCAL"})
        reg = build_registry([_provider(kind=ProviderKind.SERVICE.value, env=env)], [_capability()])
        p = reg.get_provider("prov.1")
        assert check_locality(p, RoutingPref(locality=Locality.LOCAL.value)) is None

    def test_local_request_remote_provider_rejected(self):
        reg = build_registry([_provider(kind=ProviderKind.SERVICE.value)], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_locality(p, RoutingPref(locality=Locality.LOCAL.value))
        assert reason is not None and "not local" in reason

    def test_remote_rejects_local(self):
        reg = build_registry([_provider(kind=ProviderKind.LOCAL.value)], [_capability()])
        p = reg.get_provider("prov.1")
        reason = check_locality(p, RoutingPref(locality=Locality.REMOTE.value))
        assert reason is not None and "is local" in reason


# ---------------------------------------------------------------------------
# binding eligibility
# ---------------------------------------------------------------------------

class TestBindingEligibility:
    def test_no_bindings_ineligible(self):
        reg = build_registry([_provider(bindings=[])], [_capability()])
        p = reg.get_provider("prov.1")
        assert eligible_bindings(p, reg.get_capability("cap.gen")) == []

    def test_allowlist_filter(self):
        b1 = Binding(kind=BindingType.CHAT.value, endpoint_ref="e1", binding_id="b1")
        b2 = Binding(kind=BindingType.HTTP_API.value, endpoint_ref="e2", binding_id="b2")
        reg = build_registry(
            [_provider(bindings=[b1, b2])],
            [_capability(binding_types=[BindingType.CHAT.value])],
        )
        p = reg.get_provider("prov.1")
        out = eligible_bindings(p, reg.get_capability("cap.gen"))
        assert [b.kind for b in out] == [BindingType.CHAT.value]

    def test_deterministic_sort(self):
        b3 = Binding(kind=BindingType.CHAT.value, endpoint_ref="z", binding_id="b3")
        b1 = Binding(kind=BindingType.CHAT.value, endpoint_ref="a", binding_id="b1")
        b2 = Binding(kind=BindingType.CHAT.value, endpoint_ref="m", binding_id="b2")
        reg = build_registry([_provider(bindings=[b3, b1, b2])], [_capability()])
        p = reg.get_provider("prov.1")
        out = eligible_bindings(p, reg.get_capability("cap.gen"))
        assert [b.binding_id for b in out] == ["b1", "b2", "b3"]


# ---------------------------------------------------------------------------
# aggregate provider eligibility
# ---------------------------------------------------------------------------

class TestProviderEligibility:
    def test_fully_eligible(self):
        b = Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="e", binding_id="b1")
        env = EnvironmentInfo(os="linux")
        reg = build_registry(
            [_provider(env=env, bindings=[b])],
            [_capability(binding_types=[BindingType.LOCAL_IPC.value])],
        )
        p = reg.get_provider("prov.1")
        assert provider_eligibility(p, _request(env_req=EnvironmentRequirement(os="linux")), reg) is None

    def test_no_eligible_binding(self):
        env = EnvironmentInfo(os="linux")
        reg = build_registry(
            [_provider(env=env, bindings=[])],
            [_capability(binding_types=[BindingType.LOCAL_IPC.value])],
        )
        p = reg.get_provider("prov.1")
        reason = provider_eligibility(p, _request(), reg)
        assert reason is not None and "no eligible binding" in reason
