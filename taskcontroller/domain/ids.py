"""WP0 TaskController identifier value objects and references (framework-neutral)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from taskcontroller.errors import TaskControllerValidationError

# Generic identifier shape: 1-128 chars. Allows alphanumerics, dash, underscore,
# and dot so DNS-like / path-like refs (e.g. "prov.local.chatgpt.py", "run.1")
# are valid. No whitespace or other special chars.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][-A-Za-z0-9_.]{0,127}$")
_VERSION_PATTERN = re.compile(r"^\S.{0,127}$")  # non-empty, trimmed-friendly


def _validate_id(name: str, value: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.match(value):
        raise TaskControllerValidationError(
            f"invalid {name}: {value!r} must match {_ID_PATTERN.pattern}"
        )


def _validate_version(name: str, value: str) -> None:
    if not isinstance(value, str) or not _VERSION_PATTERN.match(value):
        raise TaskControllerValidationError(
            f"invalid {name}: {value!r} must be a non-empty version string"
        )


@dataclass(frozen=True)
class ProviderRef:
    """Generic reference to any executable provider instance (local/connector/agent/...)."""

    provider_id: str

    def __post_init__(self) -> None:
        _validate_id("provider_id", self.provider_id)

    def to_dict(self) -> dict:
        return {"provider_id": self.provider_id}

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderRef":
        return cls(provider_id=d["provider_id"])


# ExecutionProviderRef is a semantic alias of ProviderRef (same shape).
ExecutionProviderRef = ProviderRef


@dataclass(frozen=True)
class CapabilityRef:
    capability_id: str

    def __post_init__(self) -> None:
        _validate_id("capability_id", self.capability_id)

    def to_dict(self) -> dict:
        return {"capability_id": self.capability_id}

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityRef":
        return cls(capability_id=d["capability_id"])


@dataclass(frozen=True)
class TaskRef:
    """Reference to a node/task within a run (and optionally a dependency)."""

    run_id: str
    node_id: str

    def __post_init__(self) -> None:
        _validate_id("run_id", self.run_id)
        _validate_id("node_id", self.node_id)

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "node_id": self.node_id}

    @classmethod
    def from_dict(cls, d: dict) -> "TaskRef":
        return cls(run_id=d["run_id"], node_id=d["node_id"])


@dataclass(frozen=True)
class ExecutionRef:
    """Reference to a concrete execution attempt (and its correlation tokens)."""

    execution_id: str
    attempt: int
    attempt_id: str
    fencing_token: str

    def __post_init__(self) -> None:
        _validate_id("execution_id", self.execution_id)
        _validate_id("attempt_id", self.attempt_id)
        if not isinstance(self.attempt, int) or self.attempt < 1:
            raise TaskControllerValidationError(
                f"invalid attempt: {self.attempt!r} must be an int >= 1"
            )
        if not isinstance(self.fencing_token, str) or not self.fencing_token:
            raise TaskControllerValidationError("fencing_token must be a non-empty string")

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "attempt_id": self.attempt_id,
            "fencing_token": self.fencing_token,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionRef":
        return cls(
            execution_id=d["execution_id"],
            attempt=d["attempt"],
            attempt_id=d["attempt_id"],
            fencing_token=d["fencing_token"],
        )


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str

    def __post_init__(self) -> None:
        _validate_id("artifact_id", self.artifact_id)

    def to_dict(self) -> dict:
        return {"artifact_id": self.artifact_id}

    @classmethod
    def from_dict(cls, d: dict) -> "ArtifactRef":
        return cls(artifact_id=d["artifact_id"])


@dataclass(frozen=True)
class BindingRef:
    binding_id: str

    def __post_init__(self) -> None:
        _validate_id("binding_id", self.binding_id)

    def to_dict(self) -> dict:
        return {"binding_id": self.binding_id}

    @classmethod
    def from_dict(cls, d: dict) -> "BindingRef":
        return cls(binding_id=d["binding_id"])


@dataclass(frozen=True)
class ProducerRef:
    """Identity of an event producer (a provider instance or actor)."""

    producer_id: str

    def __post_init__(self) -> None:
        _validate_id("producer_id", self.producer_id)

    def to_dict(self) -> dict:
        return {"producer_id": self.producer_id}

    @classmethod
    def from_dict(cls, d: dict) -> "ProducerRef":
        return cls(producer_id=d["producer_id"])
