"""TC-MBX-305: generic capability routing into a mailbox AgentInstance.

The bridge must reuse the existing pure routing snapshot and bind the selected
provider identity into the mailbox request without product-name conditionals or
logical-contract changes.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from taskcontroller.controlplane.agent_routing import (
    RoutedMailboxRequest,
    route_bounded_mailbox_request,
)
from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.domain.enums import BindingType, CostClass, Idempotency, ProviderKind, TrustTier
from taskcontroller.domain.ids import CapabilityRef
from taskcontroller.domain.models import CapabilityCard, ExecutionProviderCard
from taskcontroller.domain.values import Binding, EnvironmentInfo, EnvironmentRequirement
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.routing.errors import RoutingNoRouteError
from taskcontroller.routing.registry import build_registry


_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "path": "taskcontroller/controlplane/request_compiler.py",
    "blob_digest": "sha256:" + "1" * 64,
}


def _environment(**overrides: object) -> EnvironmentInfo:
    values: dict[str, object] = {
        "os": "darwin",
        "runtime": "python3.11",
        "arch": "arm64",
        "capabilities": ["git", "pytest"],
        "metadata": {"memory_mb": 4096, "locality": "LOCAL"},
    }
    values.update(overrides)
    return EnvironmentInfo(**values)


def _provider(
    provider_id: str,
    *,
    trust: str = TrustTier.STANDARD.value,
    environment: EnvironmentInfo | None = None,
    capability_id: str = "cap.task",
) -> ExecutionProviderCard:
    return ExecutionProviderCard(
        provider_id=provider_id,
        provider_kind=ProviderKind.AGENT.value,
        capability_refs=[CapabilityRef(capability_id)],
        environment=environment if environment is not None else _environment(),
        bindings=[
            Binding(
                kind=BindingType.HTTP_API.value,
                endpoint_ref=f"https://{provider_id}.invalid/dispatch",
                binding_id=f"{provider_id}.binding",
            )
        ],
        trust_tier=trust,
        cost_class=CostClass.MEDIUM.value,
    )


def _registry(*providers: ExecutionProviderCard):
    capability = CapabilityCard(
        capability_id="cap.task",
        name="bounded task execution",
        version="1.0.0",
        idempotency=Idempotency.IDEMPOTENT.value,
        cost_class=CostClass.MEDIUM.value,
        required_environment=EnvironmentRequirement(),
        supported_binding_types=[BindingType.HTTP_API.value],
    )
    return build_registry(list(providers), [capability])


def _bound_request(**changes: object) -> BoundedMailboxRequest:
    values: dict[str, object] = {
        "message_id": "message-305",
        "run_id": "run-305",
        "node_id": "node-305",
        "seq": 1,
        "correlation_id": "correlation-305",
        "contract_id": "contract-305",
        "plan_version": "plan-305",
        "contract_digest": "sha256:" + "2" * 64,
        "boundary_digest": "sha256:" + "3" * 64,
        "source_digest": "sha256:" + "4" * 64,
        "source_manifest_ref": "source-manifest-305",
        "objective": "Execute one bounded logical contract.",
        "scope": {
            "allowed_actions": ["read_repo", "run_tests"],
            "denied_actions": ["deploy", "merge"],
            "writable_targets": ["taskcontroller"],
            "source_roots": ["taskcontroller", "tests/taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "authority_constraints": {
            "denied_actions": ["deploy", "merge"],
            "writable_targets": ["taskcontroller"],
        },
        "acceptance_criteria": (
            "The selected alternate receives the same logical contract.",
            "The selected route is represented by generic provider data.",
        ),
        "source_refs": (_SOURCE,),
        "evidence_refs": ("evidence://tc-305",),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "5" * 64,
        },
        "standards_profile_ref": "standards.default/v1",
        "recipient_capability": "cap.task",
        "agent_instance": "agent.initial",
        "environment_requirements": {
            "os": "darwin",
            "runtime": "python3.11",
            "arch": "arm64",
            "capabilities": ["git", "pytest"],
        },
        "attempt_id": "attempt-305",
        "attempt_number": 2,
        "lease_generation": 4,
        "fencing_token": "fence-305",
        "lease_expires_at": "2026-09-11T07:00:00+07:00",
        "idempotency_key": "idem-305",
        "producer_namespace": "controller",
        "producer_actor_id": "controller-305",
        "execution_id": "execution-305",
    }
    values.update(changes)
    return BoundedMailboxRequest(**values)


def _without_route_target(envelope: object) -> dict:
    payload = copy.deepcopy(envelope.to_dict())
    payload.pop("digest", None)
    payload["recipient"].pop("agent_instance", None)
    payload["attempt"].pop("agent_instance", None)
    payload["provenance"].pop("agent_instance", None)
    payload["payload"].pop("agent_instance", None)
    return payload


class TestAgentInstanceRouting:
    def test_alternate_compatible_agent_receives_same_logical_contract(self) -> None:
        request = _bound_request()
        baseline = compile_bounded_mailbox_request(request)
        registry = _registry(
            _provider("agent.primary", trust=TrustTier.STANDARD.value),
            _provider("agent.alternate", trust=TrustTier.TRUSTED.value),
            _provider(
                "agent.incompatible",
                trust=TrustTier.TRUSTED.value,
                environment=_environment(runtime="python3.10"),
            ),
        )

        routed = route_bounded_mailbox_request(
            registry, request, receipt_id="receipt-305", accepted_at="2026-09-11T06:00:00Z"
        )

        assert isinstance(routed, RoutedMailboxRequest)
        assert routed.provider.provider_id == "agent.alternate"
        assert routed.request.agent_instance == "agent.alternate"
        assert routed.receipt.selected_provider.provider_id == "agent.alternate"
        assert routed.receipt.binding is not None
        assert routed.receipt.binding.binding_id == "agent.alternate.binding"
        assert routed.envelope.to_dict()["recipient"]["agent_instance"] == "agent.alternate"
        assert routed.envelope.to_dict()["attempt"]["agent_instance"] == "agent.alternate"
        assert routed.envelope.to_dict()["provenance"]["agent_instance"] == "agent.alternate"
        assert routed.envelope.logical_contract == baseline.logical_contract
        assert routed.envelope.execution_identity == baseline.execution_identity
        assert _without_route_target(routed.envelope) == _without_route_target(baseline)

    def test_mapping_input_uses_generic_provider_id_without_product_branching(self) -> None:
        request = _bound_request()
        routed = route_bounded_mailbox_request(
            _registry(_provider("agent.alt", trust=TrustTier.TRUSTED.value)),
            request.__dict__,
            receipt_id="receipt-305-mapping",
        )

        assert routed.request.agent_instance == "agent.alt"
        assert routed.envelope.to_dict()["recipient"]["capability"] == "cap.task"


class TestAgentInstanceRoutingFailClosed:
    def test_missing_execution_identity_is_not_synthesized(self) -> None:
        with pytest.raises(TaskControllerValidationError, match="execution_id"):
            route_bounded_mailbox_request(
                _registry(_provider("agent.alt")),
                _bound_request(execution_id=None),
                receipt_id="receipt-305-missing-execution",
            )

    def test_malformed_environment_is_rejected_before_route(self) -> None:
        with pytest.raises(TaskControllerValidationError, match="environment_requirements"):
            route_bounded_mailbox_request(
                _registry(_provider("agent.alt")),
                _bound_request(environment_requirements=["not", "an", "object"]),
                receipt_id="receipt-305-bad-environment",
            )

    def test_no_eligible_agent_instance_remains_typed_no_route(self) -> None:
        with pytest.raises(RoutingNoRouteError):
            route_bounded_mailbox_request(
                _registry(_provider("agent.other", capability_id="cap.other")),
                _bound_request(),
                receipt_id="receipt-305-no-route",
            )

    def test_bridge_contains_no_generic_kernel_hermes_name_branching(self) -> None:
        from taskcontroller.controlplane import agent_routing

        source = Path(agent_routing.__file__).read_text(encoding="utf-8")
        assert "hermes-cloud" not in source
        assert "hermes-mac" not in source
        assert "hermes-pc" not in source
        assert "if agent_instance" not in source
        assert "subprocess" not in source
        assert "requests" not in source
