"""Pure Controller bridge from a bounded mailbox input to an AgentInstance.

The bridge adapts the mailbox compiler's input to the existing capability,
environment, and trust selector.  Provider identity is data from the registry;
no product-specific runtime branch, transport call, or state mutation occurs.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
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
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope
from taskcontroller.routing.router import route
from taskcontroller.routing.registry import Registry
from taskcontroller.routing.errors import RoutingError


_ENVIRONMENT_KEYS = frozenset({"os", "runtime", "arch", "min_memory_mb", "capabilities"})


@dataclass(frozen=True)
class RoutedMailboxRequest:
    """The selected provider and the exact v2 input bound to that provider."""

    request: BoundedMailboxRequest
    execution_request: ExecutionRequest
    provider: ExecutionProviderCard
    binding: Binding
    receipt: ExecutionReceipt
    envelope: V2MailboxEnvelope

    @property
    def selected_agent_instance(self) -> str:
        """Return the generic registry identity selected for this input."""
        return self.provider.provider_id

    def __post_init__(self) -> None:
        selected_id = self.provider.provider_id
        if self.request.agent_instance != selected_id:
            raise TaskControllerValidationError(
                "routed mailbox request recipient does not match selected provider"
            )
        if self.receipt.selected_provider.provider_id != selected_id:
            raise TaskControllerValidationError(
                "route receipt does not match selected provider"
            )
        if self.envelope.to_dict()["recipient"]["agent_instance"] != selected_id:
            raise TaskControllerValidationError(
                "compiled mailbox recipient does not match selected provider"
            )


def _as_bounded_request(
    request: BoundedMailboxRequest | Mapping[str, Any],
) -> BoundedMailboxRequest:
    if isinstance(request, BoundedMailboxRequest):
        return request
    if isinstance(request, Mapping):
        return BoundedMailboxRequest.from_mapping(request)
    raise TaskControllerValidationError(
        "agent routing input must be a BoundedMailboxRequest or object mapping"
    )


def _environment_requirement(value: Any) -> EnvironmentRequirement:
    if not isinstance(value, Mapping):
        raise TaskControllerValidationError(
            "environment_requirements must be an object for agent routing"
        )
    raw = dict(value)
    unexpected = sorted(set(raw) - _ENVIRONMENT_KEYS)
    if unexpected:
        raise TaskControllerValidationError(
            "environment_requirements contains unsupported keys: "
            + ", ".join(unexpected)
        )

    for key in ("os", "runtime", "arch"):
        candidate = raw.get(key)
        if candidate is not None and (
            not isinstance(candidate, str) or not candidate.strip()
        ):
            raise TaskControllerValidationError(
                f"environment_requirements.{key} must be a non-empty string"
            )

    min_memory = raw.get("min_memory_mb")
    if min_memory is not None and (
        isinstance(min_memory, bool) or not isinstance(min_memory, int) or min_memory < 0
    ):
        raise TaskControllerValidationError(
            "environment_requirements.min_memory_mb must be an integer >= 0"
        )

    capabilities = raw.get("capabilities", [])
    if not isinstance(capabilities, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in capabilities
    ):
        raise TaskControllerValidationError(
            "environment_requirements.capabilities must be an array of non-empty strings"
        )
    if len(set(capabilities)) != len(capabilities):
        raise TaskControllerValidationError(
            "environment_requirements.capabilities must not contain duplicates"
        )

    return EnvironmentRequirement(
        os=raw.get("os"),
        runtime=raw.get("runtime"),
        arch=raw.get("arch"),
        min_memory_mb=min_memory,
        capabilities=list(capabilities),
    )


def _execution_request(request: BoundedMailboxRequest) -> ExecutionRequest:
    execution_id = request.execution_id
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise TaskControllerValidationError(
            "agent routing requires an explicit execution_id; it is never synthesized"
        )
    capability_id = request.recipient_capability
    if not isinstance(capability_id, str) or not capability_id.strip():
        raise TaskControllerValidationError(
            "agent routing requires a non-empty recipient_capability"
        )

    return ExecutionRequest(
        execution_id=execution_id,
        contract_ref=request.contract_id,
        attempt=request.attempt_number,
        attempt_id=request.attempt_id,
        fencing_token=request.fencing_token,
        capability_requirements=CapabilityRequirement(capability_id=capability_id),
        environment_requirements=_environment_requirement(request.environment_requirements),
        routing_preferences=RoutingPref(),
        plan_version=request.plan_version,
    )


def _non_target_shape(envelope: V2MailboxEnvelope) -> dict[str, Any]:
    """Project out only provider-target fields and the derived envelope digest."""
    candidate = copy.deepcopy(envelope.to_dict())
    candidate.pop("digest", None)
    for section_name in ("recipient", "attempt", "provenance"):
        section = candidate.get(section_name)
        if isinstance(section, Mapping):
            normalized_section = dict(section)
            normalized_section.pop("agent_instance", None)
            candidate[section_name] = normalized_section
    payload = candidate.get("payload")
    if isinstance(payload, Mapping):
        normalized_payload = dict(payload)
        normalized_payload.pop("agent_instance", None)
        candidate["payload"] = normalized_payload
    return candidate


def _selected_binding(
    provider: ExecutionProviderCard, receipt: ExecutionReceipt
) -> Binding:
    if receipt.binding is None:
        raise RoutingError("selected route has no binding reference")
    for binding in provider.bindings:
        if binding.binding_id == receipt.binding.binding_id:
            return binding
    raise RoutingError("route binding reference is not present on selected provider")


def route_bounded_mailbox_request(
    registry: Registry,
    request: BoundedMailboxRequest | Mapping[str, Any],
    *,
    receipt_id: str,
    accepted_at: str | None = None,
) -> RoutedMailboxRequest:
    """Select and bind a generic provider for one bounded mailbox input.

    The input's existing target is treated as a transport-neutral placeholder;
    the selected registry ``provider_id`` is the only field replaced.  The
    original and routed envelopes must have identical non-target content.
    """
    bounded = _as_bounded_request(request)
    execution_request = _execution_request(bounded)
    baseline_envelope = compile_bounded_mailbox_request(bounded)

    receipt = route(registry, execution_request, receipt_id, accepted_at)
    if not isinstance(receipt, ExecutionReceipt):
        raise RoutingError("route did not return an ExecutionReceipt")

    provider = registry.get_provider(receipt.selected_provider.provider_id)
    if provider is None:
        raise RoutingError("route receipt references an unknown provider")
    binding = _selected_binding(provider, receipt)

    routed_request = replace(bounded, agent_instance=provider.provider_id)
    routed_envelope = compile_bounded_mailbox_request(routed_request)
    if _non_target_shape(routed_envelope) != _non_target_shape(baseline_envelope):
        raise TaskControllerValidationError(
            "agent routing changed the bounded logical contract"
        )

    return RoutedMailboxRequest(
        request=routed_request,
        execution_request=execution_request,
        provider=provider,
        binding=binding,
        receipt=receipt,
        envelope=routed_envelope,
    )


def route_mailbox_request(
    registry: Registry,
    request: BoundedMailboxRequest | Mapping[str, Any],
    *,
    receipt_id: str,
    accepted_at: str | None = None,
) -> RoutedMailboxRequest:
    """Descriptive alias for the bounded mailbox routing entrypoint."""
    return route_bounded_mailbox_request(
        registry, request, receipt_id=receipt_id, accepted_at=accepted_at
    )


__all__ = [
    "RoutedMailboxRequest",
    "route_bounded_mailbox_request",
    "route_mailbox_request",
]
