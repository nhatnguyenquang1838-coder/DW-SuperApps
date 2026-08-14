"""WP4 S1 focused tests: adapter ports, registry, envelopes (NO GWC).

Covers: immutable command/ack/signal types, explicit adapter port, deterministic
registration/lookup, no effects. Adversarial: duplicate adapter key conflict,
identical registration idempotent, unsupported binding, canonical fingerprint
stable, input order irrelevant.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import BindingType
from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import (
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
from taskcontroller.execution.errors import (
    AdapterNotFoundError,
    ExecutionFabricError,
)
from taskcontroller.execution.ports import ExecutionAdapter, FakeExecutionAdapter
from taskcontroller.execution.registry import AdapterRegistry, build_registry
from taskcontroller.execution.types import (
    AdapterSignal,
    CancelAck,
    DispatchAck,
    DispatchEnvelope,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _env():
    return ExecutionRequest(
        execution_id="exec.1",
        contract_ref="tc.1",
        attempt=1,
        attempt_id="att.1",
        fencing_token="ft-1",
        capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
    )


def _receipt():
    return ExecutionReceipt(
        receipt_id="rcpt.1",
        contract_ref="tc.1",
        execution_ref=ExecutionRef(
            execution_id="exec.1", attempt=1, attempt_id="att.1", fencing_token="ft-1"
        ),
        selected_provider=ProviderRef(provider_id="prov.1"),
        binding=BindingRef(binding_id="b1"),
        status="ROUTING",
    )


def _envelope(command_id="cmd.1", lease_id="lease.1", fencing="ft-1"):
    return DispatchEnvelope(
        command_id=command_id,
        request=_env(),
        receipt=_receipt(),
        provider=ProviderRef(provider_id="prov.1"),
        binding=BindingRef(binding_id="b1"),
        lease_id=lease_id,
        fencing_token=fencing,
        adapter_key="fake.1",
    )


# ---------------------------------------------------------------------------
# types immutable / canonical fingerprint stable
# ---------------------------------------------------------------------------

class TestTypes:
    def test_envelope_is_frozen(self):
        env = _envelope()
        with pytest.raises(Exception):
            env.command_id = "mutated"  # type: ignore[misc]

    def test_canonical_fingerprint_stable(self):
        a = _envelope().canonical_fingerprint()
        b = _envelope().canonical_fingerprint()
        assert a == b

    def test_ack_frozen(self):
        ack = DispatchAck(command_id="c1", accepted=True, status="ACCEPTED", adapter_key="k")
        with pytest.raises(Exception):
            ack.status = "REJECTED"  # type: ignore[misc]

    def test_signal_carries_explicit_fields(self):
        sig = AdapterSignal(
            event_id="ev.1",
            event_type="TASK_STARTED",
            sequence=0,
            execution_ref=ExecutionRef("exec.1", 1, "att.1", "ft-1"),
            node_id="n1",
            run_id="run.1",
            fencing_token="ft-1",
            provider_id="prov.1",
        )
        assert sig.event_id == "ev.1"
        assert sig.execution_ref.attempt_id == "att.1"


# ---------------------------------------------------------------------------
# adapter port (fake is deterministic, no I/O)
# ---------------------------------------------------------------------------

class TestAdapterPort:
    def test_fake_dispatch_accepted(self):
        a = FakeExecutionAdapter()
        ack = a.dispatch(_envelope())
        assert ack.accepted is True
        assert ack.status == "ACCEPTED"
        assert len(a.dispatched) == 1

    def test_fake_supports_cancel(self):
        a = FakeExecutionAdapter()
        assert a.supports_cancel() is True
        cack = a.cancel(_envelope())
        assert isinstance(cack, CancelAck)
        assert cack.status == "ACCEPTED"

    def test_reject_next_dispatch(self):
        a = FakeExecutionAdapter()
        a.set_reject_next_dispatch()
        ack = a.dispatch(_envelope())
        assert ack.status == "REJECTED"

    def test_abstract_adapter_cancel_unsupported(self):
        class Partial(ExecutionAdapter):
            supported_binding_types = (BindingType.LOCAL_IPC.value,)
            def dispatch(self, envelope):  # pragma: no cover - abstract impl
                return DispatchAck(command_id=envelope.command_id, accepted=True,
                                   status="ACCEPTED", adapter_key="p")
        p = Partial()
        assert p.supports_cancel() is False
        with pytest.raises(Exception):
            p.cancel(_envelope())


# ---------------------------------------------------------------------------
# registry semantics
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_duplicate_key_conflict(self):
        a1 = FakeExecutionAdapter(adapter_key="k1")
        a2 = FakeExecutionAdapter(adapter_key="k1")
        with pytest.raises(ExecutionFabricError, match="duplicate adapter_key"):
            build_registry([a1, a2])

    def test_identical_instance_idempotent(self):
        a = FakeExecutionAdapter(adapter_key="k1")
        reg = build_registry([a, a])
        assert len(reg.adapters) == 1

    def test_input_order_irrelevant(self):
        a1 = FakeExecutionAdapter(adapter_key="k.a")
        a2 = FakeExecutionAdapter(adapter_key="k.b")
        reg1 = build_registry([a1, a2])
        reg2 = build_registry([a2, a1])
        assert reg1.adapter_keys() == reg2.adapter_keys()

    def test_lookup_by_key(self):
        a = FakeExecutionAdapter(adapter_key="k1")
        reg = build_registry([a])
        assert reg.lookup_by_key("k1") is a

    def test_lookup_by_key_missing(self):
        reg = build_registry([FakeExecutionAdapter(adapter_key="k1")])
        with pytest.raises(AdapterNotFoundError):
            reg.lookup_by_key("missing")

    def test_lookup_by_binding_type(self):
        a = FakeExecutionAdapter(adapter_key="k1", binding_type=BindingType.LOCAL_IPC.value)
        reg = build_registry([a])
        found = reg.lookup_by_binding_type(BindingType.LOCAL_IPC.value)
        assert found is a

    def test_lookup_by_binding_type_unsupported(self):
        a = FakeExecutionAdapter(adapter_key="k1", binding_type=BindingType.LOCAL_IPC.value)
        reg = build_registry([a])
        with pytest.raises(AdapterNotFoundError):
            reg.lookup_by_binding_type(BindingType.HTTP_API.value)

    def test_immutable_registry(self):
        # The registry snapshot is frozen: the .adapters field cannot be rebound.
        reg = AdapterRegistry(adapters={"k1": FakeExecutionAdapter(adapter_key="k1")})
        with pytest.raises(Exception):
            reg.adapters = {"k2": FakeExecutionAdapter(adapter_key="k2")}  # type: ignore[misc]
        # Rebuilding from the same inputs yields an equal snapshot (deterministic)
        a = FakeExecutionAdapter(adapter_key="k1")
        assert build_registry([a]).to_dict() == build_registry([a]).to_dict()
