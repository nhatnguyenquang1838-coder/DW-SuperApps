"""WP0 TaskController dataclass <-> dict JSON round-trip helpers."""

from __future__ import annotations

from taskcontroller.domain.models import (
    AgentEvent,
    Artifact,
    CapabilityCard,
    ControllerDecision,
    ControllerHostProfile,
    ExecutionProviderCard,
    ExecutionReceipt,
    ExecutionRequest,
    ReviewResult,
    TaskContract,
    TeamRunState,
    WorkLease,
)
from taskcontroller.errors import TaskControllerValidationError

_MODEL_BY_NAME = {
    "controller_host_profile": ControllerHostProfile,
    "capability_card": CapabilityCard,
    "execution_provider_card": ExecutionProviderCard,
    "task_contract": TaskContract,
    "execution_request": ExecutionRequest,
    "execution_receipt": ExecutionReceipt,
    "agent_event": AgentEvent,
    "artifact": Artifact,
    "review_result": ReviewResult,
    "work_lease": WorkLease,
    "team_run_state": TeamRunState,
    "controller_decision": ControllerDecision,
}


def to_dict(obj) -> dict:
    return obj.to_dict()


def from_dict(name: str, d: dict):
    """Deserialize a dict into a model, surfacing malformed payloads as
    ``TaskControllerValidationError`` (chaining the original cause)."""
    if name not in _MODEL_BY_NAME:
        raise TaskControllerValidationError(f"unknown model name: {name!r}")
    try:
        return _MODEL_BY_NAME[name].from_dict(d)
    except TaskControllerValidationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise TaskControllerValidationError(
            f"deserialization failed for {name}: {exc}"
        ) from exc


def model_names() -> list[str]:
    return list(_MODEL_BY_NAME.keys())
