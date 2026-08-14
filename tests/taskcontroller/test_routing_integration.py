"""WP3 integration: end-to-end pure route() path (NO GWC, NO dispatch).

Locks the orchestration: Registry + ExecutionRequest + caller identity/time ->
exactly one ExecutionReceipt, or a typed RoutingNoRouteError. No network/random/
clock, no WP2 runtime/lease mutation.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import (
    BindingType,
    CostClass,
    ExecutionStatus,
    Idempotency,
    Locality,
    ProviderKind,
    TrustTier,
)
from taskcontroller.domain.ids import CapabilityRef
from taskcontroller.domain.models import CapabilityCard, ExecutionProviderCard, ExecutionRequest
from taskcontroller.domain.values import (
    Binding,
    CapabilityRequirement,
    EnvironmentRequirement,
    RoutingPref,
)
from taskcontroller.routing.errors import RoutingNoRouteError
from taskcontroller.routing.registry import build_registry
from taskcontroller.routing.router import route
from taskcontroller.validation import validate


def _registry():
    cap = CapabilityCard(
        capability_id="cap.gen",
        name="gen",
        version="1.0.0",
        idempotency=Idempotency.IDEMPOTENT.value,
        cost_class=CostClass.FREE.value,
        required_environment=EnvironmentRequirement(),
        supported_binding_types=[BindingType.LOCAL_IPC.value],
    )
    prov = ExecutionProviderCard(
        provider_id="prov.1",
        provider_kind=ProviderKind.LOCAL.value,
        capability_refs=[CapabilityRef("cap.gen")],
        environment=None,
        bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://l", binding_id="b1")],
        trust_tier=TrustTier.STANDARD.value,
        cost_class=CostClass.FREE.value,
    )
    return build_registry([prov], [cap])


def _request():
    return ExecutionRequest(
        execution_id="exec.1",
        contract_ref="tc.1",
        attempt=2,
        attempt_id="att.1",
        fencing_token="ft-1",
        capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
    )


class TestRouteIntegration:
    def test_route_produces_valid_receipt(self):
        reg = _registry()
        req = _request()
        receipt = route(reg, req, "rcpt.1", "2026-01-01T00:00:00Z")
        # exact correlation preserved
        assert receipt.contract_ref == "tc.1"
        assert receipt.execution_ref.execution_id == "exec.1"
        assert receipt.execution_ref.attempt == 2
        assert receipt.execution_ref.attempt_id == "att.1"
        assert receipt.execution_ref.fencing_token == "ft-1"
        assert receipt.selected_provider.provider_id == "prov.1"
        assert receipt.binding is not None and receipt.binding.binding_id == "b1"
        assert receipt.status == ExecutionStatus.ROUTING.value
        assert receipt.accepted_at == "2026-01-01T00:00:00Z"
        # WP0 schema valid
        validate("execution_receipt", receipt.to_dict())

    def test_route_idempotent_for_same_inputs(self):
        reg = _registry()
        req = _request()
        a = route(reg, req, "rcpt.1", "t").to_dict()
        b = route(reg, req, "rcpt.1", "t").to_dict()
        assert a == b

    def test_route_no_eligible_provider_typed_error(self):
        reg = _registry()
        req = ExecutionRequest(
            execution_id="exec.2",
            contract_ref="tc.2",
            attempt=1,
            attempt_id="att.2",
            fencing_token="ft-2",
            capability_requirements=CapabilityRequirement(capability_id="cap.missing"),
            environment_requirements=EnvironmentRequirement(),
            routing_preferences=RoutingPref(),
        )
        with pytest.raises(RoutingNoRouteError):
            route(reg, req, "rcpt.2")
