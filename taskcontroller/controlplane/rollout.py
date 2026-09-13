"""Pure staged protocol enablement for one generic AgentInstance.

The policy is intentionally decision-only.  It reads explicit capability
advertisement and an explicit project/runtime flag, then returns a canonical
protocol choice or a closed blocked decision.  It never constructs a new
request, changes a run record, or invokes a provider.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V1_PROTOCOL, V2_PROTOCOL


DEFAULT_V2_CAPABILITY = "taskcontroller.mailbox.v2"


class RolloutMode(str, Enum):
    """Staged rollout policy for one AgentInstance lane."""

    V1_ONLY = "V1_ONLY"
    V2_PREFERRED = "V2_PREFERRED"
    V2_REQUIRED = "V2_REQUIRED"


class RolloutDisposition(str, Enum):
    """Machine-readable outcome of the pure rollout decision."""

    V2_SELECTED = "V2_SELECTED"
    V1_FALLBACK = "V1_FALLBACK"
    BLOCKED = "BLOCKED"


def _strict_bool(value: Any, field_name: str) -> bool:
    if type(value) is not bool:
        raise TaskControllerValidationError(f"{field_name} must be a boolean")
    return value


def _non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RolloutConfig:
    """Explicit per-lane rollout controls; no environment discovery is used."""

    mode: RolloutMode = RolloutMode.V2_PREFERRED
    feature_flag: bool = False
    v2_capability: str = DEFAULT_V2_CAPABILITY

    def __post_init__(self) -> None:
        try:
            mode = RolloutMode(self.mode)
        except (TypeError, ValueError):
            raise TaskControllerValidationError(
                f"mode must be one of {tuple(item.value for item in RolloutMode)}"
            ) from None
        object.__setattr__(self, "mode", mode)
        _strict_bool(self.feature_flag, "feature_flag")
        _non_empty_text(self.v2_capability, "v2_capability")


@dataclass(frozen=True)
class RolloutDecision:
    """A protocol choice bound to the exact caller-owned legacy request."""

    disposition: RolloutDisposition
    protocol: str | None
    code: str
    request: Any
    v2_enabled: bool
    capability_enabled: bool
    feature_flag_enabled: bool
    v2_available: bool
    request_v2_supported: bool
    agent_instance_id: str | None

    def __post_init__(self) -> None:
        try:
            disposition = RolloutDisposition(self.disposition)
        except (TypeError, ValueError):
            raise TaskControllerValidationError("invalid rollout disposition") from None
        object.__setattr__(self, "disposition", disposition)
        _non_empty_text(self.code, "code")
        if self.request is None:
            raise TaskControllerValidationError("request must not be None")
        for field_name in (
            "v2_enabled",
            "capability_enabled",
            "feature_flag_enabled",
            "v2_available",
            "request_v2_supported",
        ):
            _strict_bool(getattr(self, field_name), field_name)
        if self.agent_instance_id is not None:
            _non_empty_text(self.agent_instance_id, "agent_instance_id")

        if disposition is RolloutDisposition.V2_SELECTED:
            if self.protocol != V2_PROTOCOL:
                raise TaskControllerValidationError(
                    "V2_SELECTED must carry the canonical v2 protocol"
                )
        elif disposition is RolloutDisposition.V1_FALLBACK:
            if self.protocol != V1_PROTOCOL:
                raise TaskControllerValidationError(
                    "V1_FALLBACK must carry the canonical v1 protocol"
                )
        elif self.protocol is not None:
            raise TaskControllerValidationError("BLOCKED must not carry a protocol")

    @property
    def fallback_to_v1(self) -> bool:
        return self.disposition is RolloutDisposition.V1_FALLBACK

    @property
    def blocked(self) -> bool:
        return self.disposition is RolloutDisposition.BLOCKED


def _agent_identity_and_capabilities(
    agent_instance: Any,
) -> tuple[str | None, frozenset[str]]:
    """Read generic provider data without resolving or probing a runtime."""
    if agent_instance is None:
        return None, frozenset()

    if isinstance(agent_instance, Mapping):
        agent_id = agent_instance.get("provider_id")
        refs = agent_instance.get("capability_refs", ())
    else:
        agent_id = getattr(agent_instance, "provider_id", None)
        refs = getattr(agent_instance, "capability_refs", None)
        if refs is None:
            raise TaskControllerValidationError(
                "agent_instance must expose capability_refs"
            )

    if agent_id is not None:
        _non_empty_text(agent_id, "agent_instance.provider_id")
    if isinstance(refs, (str, bytes)) or not isinstance(refs, Sequence):
        raise TaskControllerValidationError(
            "agent_instance.capability_refs must be a sequence"
        )

    capability_ids: set[str] = set()
    for index, reference in enumerate(refs):
        if isinstance(reference, str):
            capability_id = reference
        elif isinstance(reference, Mapping):
            capability_id = reference.get("capability_id")
        else:
            capability_id = getattr(reference, "capability_id", None)
        capability_id = _non_empty_text(
            capability_id, f"agent_instance.capability_refs[{index}].capability_id"
        )
        capability_ids.add(capability_id)

    return agent_id, frozenset(capability_ids)


def _decision(
    *,
    disposition: RolloutDisposition,
    protocol: str | None,
    code: str,
    request: Any,
    v2_enabled: bool,
    capability_enabled: bool,
    feature_flag_enabled: bool,
    v2_available: bool,
    request_v2_supported: bool,
    agent_instance_id: str | None,
) -> RolloutDecision:
    return RolloutDecision(
        disposition=disposition,
        protocol=protocol,
        code=code,
        request=request,
        v2_enabled=v2_enabled,
        capability_enabled=capability_enabled,
        feature_flag_enabled=feature_flag_enabled,
        v2_available=v2_available,
        request_v2_supported=request_v2_supported,
        agent_instance_id=agent_instance_id,
    )


def decide_rollout(
    agent_instance: Any,
    request: Any,
    *,
    config: RolloutConfig | None = None,
    v2_available: bool = True,
    request_v2_supported: bool = True,
) -> RolloutDecision:
    """Choose v2, fall back to v1, or block without mutating ``request``.

    ``v2_available`` and ``request_v2_supported`` are explicit Controller-side
    facts.  This function never infers them from the request or discovers them
    from a runtime.  A preferred lane uses v1 when either fact is false; a
    required lane returns ``BLOCKED`` so a caller cannot silently downgrade.
    """
    if request is None:
        raise TaskControllerValidationError("request must not be None")
    rollout = config if config is not None else RolloutConfig()
    if not isinstance(rollout, RolloutConfig):
        raise TaskControllerValidationError("config must be a RolloutConfig")
    _strict_bool(v2_available, "v2_available")
    _strict_bool(request_v2_supported, "request_v2_supported")

    agent_id, capabilities = _agent_identity_and_capabilities(agent_instance)
    capability_enabled = rollout.v2_capability in capabilities
    feature_flag_enabled = rollout.feature_flag
    explicit_enablement = capability_enabled or feature_flag_enabled
    v2_enabled = rollout.mode is not RolloutMode.V1_ONLY and explicit_enablement

    if rollout.mode is RolloutMode.V1_ONLY:
        return _decision(
            disposition=RolloutDisposition.V1_FALLBACK,
            protocol=V1_PROTOCOL,
            code="V2_DISABLED",
            request=request,
            v2_enabled=False,
            capability_enabled=capability_enabled,
            feature_flag_enabled=feature_flag_enabled,
            v2_available=v2_available,
            request_v2_supported=request_v2_supported,
            agent_instance_id=agent_id,
        )

    if not explicit_enablement:
        disposition = (
            RolloutDisposition.BLOCKED
            if rollout.mode is RolloutMode.V2_REQUIRED
            else RolloutDisposition.V1_FALLBACK
        )
        return _decision(
            disposition=disposition,
            protocol=None if disposition is RolloutDisposition.BLOCKED else V1_PROTOCOL,
            code="V2_NOT_ENABLED",
            request=request,
            v2_enabled=False,
            capability_enabled=capability_enabled,
            feature_flag_enabled=feature_flag_enabled,
            v2_available=v2_available,
            request_v2_supported=request_v2_supported,
            agent_instance_id=agent_id,
        )

    for supported, code in (
        (v2_available, "V2_UNAVAILABLE"),
        (request_v2_supported, "V2_REQUEST_UNSUPPORTED"),
    ):
        if not supported:
            disposition = (
                RolloutDisposition.BLOCKED
                if rollout.mode is RolloutMode.V2_REQUIRED
                else RolloutDisposition.V1_FALLBACK
            )
            return _decision(
                disposition=disposition,
                protocol=(
                    None
                    if disposition is RolloutDisposition.BLOCKED
                    else V1_PROTOCOL
                ),
                code=code,
                request=request,
                v2_enabled=v2_enabled,
                capability_enabled=capability_enabled,
                feature_flag_enabled=feature_flag_enabled,
                v2_available=v2_available,
                request_v2_supported=request_v2_supported,
                agent_instance_id=agent_id,
            )

    return _decision(
        disposition=RolloutDisposition.V2_SELECTED,
        protocol=V2_PROTOCOL,
        code="V2_SELECTED",
        request=request,
        v2_enabled=True,
        capability_enabled=capability_enabled,
        feature_flag_enabled=feature_flag_enabled,
        v2_available=v2_available,
        request_v2_supported=request_v2_supported,
        agent_instance_id=agent_id,
    )


__all__ = [
    "DEFAULT_V2_CAPABILITY",
    "RolloutConfig",
    "RolloutDecision",
    "RolloutDisposition",
    "RolloutMode",
    "decide_rollout",
]
