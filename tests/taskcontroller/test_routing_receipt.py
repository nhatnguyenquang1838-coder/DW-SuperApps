"""WP3 S3 focused tests: ExecutionReceipt compiler (NO GWC, NO dispatch).

Tests:
- execution/attempt/fencing exact preservation
- provider/binding exact preservation
- caller-supplied receipt_id + accepted_at only (router generates neither)
- schema-valid round trip via canonical WP0 validate() + from_dict()
- invalid/mismatched route rejected (defensive)
- same inputs => same receipt (determinism)
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import BindingType, CostClass, ExecutionStatus, Idempotency, ProviderKind, TrustTier
from taskcontroller.domain.ids import CapabilityRef
from taskcontroller.domain.models import (
    CapabilityCard,
    ExecutionProviderCard,
    ExecutionReceipt,
    ExecutionRequest,
)
from taskcontroller.domain.values import (
    Binding,
    CapabilityRequirement,
    EnvironmentRequirement,
    RoutingPref,
)
from taskcontroller.routing.errors import RoutingError
from taskcontroller.routing.receipt import compile_receipt
from taskcontroller.validation import validate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cap():
    return CapabilityCard(
        capability_id="cap.gen",
        name="gen",
        version="1.0.0",
        idempotency=Idempotency.IDEMPOTENT.value,
        cost_class=CostClass.FREE.value,
        required_environment=EnvironmentRequirement(),
        supported_binding_types=[BindingType.LOCAL_IPC.value],
    )


def _provider(pid="prov.1"):
    return ExecutionProviderCard(
        provider_id=pid,
        provider_kind=ProviderKind.LOCAL.value,
        capability_refs=[CapabilityRef("cap.gen")],
        environment=None,
        bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://local", binding_id="bind.1")],
        trust_tier=TrustTier.STANDARD.value,
        cost_class=CostClass.FREE.value,
    )


def _binding():
    return Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://local", binding_id="bind.1")


def _request():
    return ExecutionRequest(
        execution_id="exec.abc",
        contract_ref="tc.xyz",
        attempt=3,
        attempt_id="att.789",
        fencing_token="ft-token-1",
        capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
    )


# ---------------------------------------------------------------------------
# exact correlation preservation
# ---------------------------------------------------------------------------

class TestReceiptCorrelation:
    def test_execution_attempt_fencing_preserved(self):
        req = _request()
        r = compile_receipt(req, _provider(), _binding(), "rcpt.1", "2026-01-01T00:00:00Z")
        assert r.contract_ref == "tc.xyz"
        assert r.execution_ref.execution_id == "exec.abc"
        assert r.execution_ref.attempt == 3
        assert r.execution_ref.attempt_id == "att.789"
        assert r.execution_ref.fencing_token == "ft-token-1"

    def test_provider_binding_preserved(self):
        r = compile_receipt(_request(), _provider("prov.win"), _binding(), "rcpt.1")
        assert r.selected_provider.provider_id == "prov.win"
        assert r.binding is not None and r.binding.binding_id == "bind.1"

    def test_status_routing_not_dispatched(self):
        r = compile_receipt(_request(), _provider(), _binding(), "rcpt.1")
        assert r.status == ExecutionStatus.ROUTING.value
        assert r.status != ExecutionStatus.DISPATCHED.value

    def test_caller_supplied_identity_time_only(self):
        r = compile_receipt(_request(), _provider(), _binding(), "rcpt.caller", "2026-02-02T02:02:02Z")
        assert r.receipt_id == "rcpt.caller"
        assert r.accepted_at == "2026-02-02T02:02:02Z"

    def test_accepted_at_none_allowed(self):
        r = compile_receipt(_request(), _provider(), _binding(), "rcpt.1", None)
        assert r.accepted_at is None


# ---------------------------------------------------------------------------
# schema-valid round trip (canonical WP0)
# ---------------------------------------------------------------------------

class TestReceiptSchemaRoundTrip:
    def test_schema_valid(self):
        r = compile_receipt(_request(), _provider(), _binding(), "rcpt.1", "2026-01-01T00:00:00Z")
        d = r.to_dict()
        validate("execution_receipt", d)  # raises if invalid

    def test_round_trip_equals(self):
        r = compile_receipt(_request(), _provider(), _binding(), "rcpt.1", "2026-01-01T00:00:00Z")
        d = r.to_dict()
        restored = ExecutionReceipt.from_dict(d)
        assert restored == r
        # and re-validates
        validate("execution_receipt", restored.to_dict())

    def test_from_dict_canonical_helper(self):
        from taskcontroller import from_dict
        r = compile_receipt(_request(), _provider(), _binding(), "rcpt.1")
        d = r.to_dict()
        again = from_dict("execution_receipt", d)
        assert again.execution_ref.fencing_token == "ft-token-1"


# ---------------------------------------------------------------------------
# defensive / determinism
# ---------------------------------------------------------------------------

class TestReceiptDefensive:
    def test_invalid_route_none_binding_rejected(self):
        with pytest.raises(RoutingError):
            compile_receipt(_request(), _provider(), None, "rcpt.1")

    def test_invalid_route_wrong_provider_type_rejected(self):
        with pytest.raises(RoutingError):
            compile_receipt(_request(), "not-a-provider", _binding(), "rcpt.1")

    def test_same_inputs_same_receipt(self):
        a = compile_receipt(_request(), _provider(), _binding(), "rcpt.1", "t")
        b = compile_receipt(_request(), _provider(), _binding(), "rcpt.1", "t")
        assert a.to_dict() == b.to_dict()
