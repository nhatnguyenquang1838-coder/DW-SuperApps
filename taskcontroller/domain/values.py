"""WP0 TaskController supporting value objects (framework-neutral, JSON-serializable)."""

from __future__ import annotations

from dataclasses import dataclass, field

from taskcontroller.domain.enums import (
    ActorKind,
    BindingType,
    CostClass,
    Idempotency,
    Locality,
    Priority,
    TrustTier,
    as_enum,
)
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.errors import TaskControllerValidationError


@dataclass
class Binding:
    """Generic communication binding. A local provider may have none.

    `protocol`/`protocol_version` reserve space so A2A-over-Slack, HTTP A2A,
    local IPC, MCP/connector, etc. map without product literals in core.
    """

    kind: str
    endpoint_ref: str
    protocol: str | None = None
    protocol_version: str | None = None
    auth_ref: str | None = None
    binding_id: str | None = None

    def __post_init__(self) -> None:
        as_enum(BindingType, self.kind, 'kind')  # validates against enum
        if not isinstance(self.endpoint_ref, str) or not self.endpoint_ref:
            raise TaskControllerValidationError("binding.endpoint_ref must be non-empty")

    def to_dict(self) -> dict:
        d = {
            "kind": self.kind,
            "endpoint_ref": self.endpoint_ref,
        }
        if self.protocol is not None:
            d["protocol"] = self.protocol
        if self.protocol_version is not None:
            d["protocol_version"] = self.protocol_version
        if self.auth_ref is not None:
            d["auth_ref"] = self.auth_ref
        if self.binding_id is not None:
            d["binding_id"] = self.binding_id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Binding":
        return cls(
            kind=d["kind"],
            endpoint_ref=d["endpoint_ref"],
            protocol=d.get("protocol"),
            protocol_version=d.get("protocol_version"),
            auth_ref=d.get("auth_ref"),
            binding_id=d.get("binding_id"),
        )


@dataclass
class ScopeSpec:
    """Allowed work and forbidden actions bounding a task contract."""

    allowed_work: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    boundaries: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"allowed_work": self.allowed_work, "forbidden_actions": self.forbidden_actions}
        if self.boundaries:
            d["boundaries"] = self.boundaries
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScopeSpec":
        return cls(
            allowed_work=d.get("allowed_work", []),
            forbidden_actions=d.get("forbidden_actions", []),
            boundaries=d.get("boundaries", {}),
        )


@dataclass
class EvidenceSpec:
    """One required evidence item for contract acceptance."""

    evidence_id: str
    description: str
    artifact_ref: str | None = None

    def to_dict(self) -> dict:
        d = {"evidence_id": self.evidence_id, "description": self.description}
        if self.artifact_ref is not None:
            d["artifact_ref"] = self.artifact_ref
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceSpec":
        return cls(
            evidence_id=d["evidence_id"],
            description=d["description"],
            artifact_ref=d.get("artifact_ref"),
        )


@dataclass
class ReportingSpec:
    """Reporting milestones and after-report behavior."""

    milestones: list[str] = field(default_factory=list)
    after_report: str | None = None  # e.g. "HALT", "AWAIT_REVIEW", "CONTINUE"

    def to_dict(self) -> dict:
        d: dict = {"milestones": self.milestones}
        if self.after_report is not None:
            d["after_report"] = self.after_report
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ReportingSpec":
        return cls(milestones=d.get("milestones", []), after_report=d.get("after_report"))


@dataclass
class CapabilityRequirement:
    """Compiled capability requirement for an execution attempt."""

    capability_id: str
    min_version: str | None = None
    idempotency: str | None = None
    cost_class: str | None = None

    def __post_init__(self) -> None:
        if self.idempotency is not None:
            as_enum(Idempotency, self.idempotency, 'idempotency')
        if self.cost_class is not None:
            as_enum(CostClass, self.cost_class, 'cost_class')

    def to_dict(self) -> dict:
        d = {"capability_id": self.capability_id}
        if self.min_version is not None:
            d["min_version"] = self.min_version
        if self.idempotency is not None:
            d["idempotency"] = self.idempotency
        if self.cost_class is not None:
            d["cost_class"] = self.cost_class
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityRequirement":
        return cls(
            capability_id=d["capability_id"],
            min_version=d.get("min_version"),
            idempotency=d.get("idempotency"),
            cost_class=d.get("cost_class"),
        )


@dataclass
class EnvironmentRequirement:
    """Required runtime/environment characteristics."""

    os: str | None = None
    runtime: str | None = None  # e.g. "python3.11", "node18"
    arch: str | None = None
    min_memory_mb: int | None = None
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {}
        for k in ("os", "runtime", "arch"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        if self.min_memory_mb is not None:
            d["min_memory_mb"] = self.min_memory_mb
        if self.capabilities:
            d["capabilities"] = self.capabilities
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EnvironmentRequirement":
        return cls(
            os=d.get("os"),
            runtime=d.get("runtime"),
            arch=d.get("arch"),
            min_memory_mb=d.get("min_memory_mb"),
            capabilities=d.get("capabilities", []),
        )


@dataclass
class RoutingPref:
    """Attempt routing preferences (not a permanent host binding)."""

    locality: str = "ANY"
    remote_fallback: bool = True
    preferred_kinds: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        as_enum(Locality, self.locality, 'locality')
        # validate preferred provider kinds if provided
        for k in self.preferred_kinds:
            from taskcontroller.domain.enums import ProviderKind

            as_enum(ProviderKind, k, 'preferred_kinds')

    def to_dict(self) -> dict:
        d = {"locality": self.locality, "remote_fallback": self.remote_fallback}
        if self.preferred_kinds:
            d["preferred_kinds"] = self.preferred_kinds
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RoutingPref":
        return cls(
            locality=d.get("locality", "ANY"),
            remote_fallback=d.get("remote_fallback", True),
            preferred_kinds=d.get("preferred_kinds", []),
        )


@dataclass
class InputRef:
    """Exact input/source reference for an execution attempt."""

    input_id: str
    source_ref: str
    media_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.input_id, str) or not self.input_id:
            raise TaskControllerValidationError("input_ref.input_id must be non-empty")
        if not isinstance(self.source_ref, str) or not self.source_ref:
            raise TaskControllerValidationError("input_ref.source_ref must be non-empty")

    def to_dict(self) -> dict:
        d = {"input_id": self.input_id, "source_ref": self.source_ref}
        if self.media_type is not None:
            d["media_type"] = self.media_type
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InputRef":
        return cls(
            input_id=d["input_id"],
            source_ref=d["source_ref"],
            media_type=d.get("media_type"),
        )


@dataclass
class Permission:
    """Permissions / boundaries granted to an execution attempt."""

    boundaries: list[str] = field(default_factory=list)
    allowlist: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {}
        if self.boundaries:
            d["boundaries"] = self.boundaries
        if self.allowlist:
            d["allowlist"] = self.allowlist
        if self.deny:
            d["deny"] = self.deny
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Permission":
        return cls(
            boundaries=d.get("boundaries", []),
            allowlist=d.get("allowlist", []),
            deny=d.get("deny", []),
        )


@dataclass
class ArtifactSpec:
    """Expected output artifact shape for an execution attempt."""

    artifact_id: str
    media_type: str | None = None
    schema_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id:
            raise TaskControllerValidationError("artifact_spec.artifact_id must be non-empty")

    def to_dict(self) -> dict:
        d = {"artifact_id": self.artifact_id}
        if self.media_type is not None:
            d["media_type"] = self.media_type
        if self.schema_ref is not None:
            d["schema_ref"] = self.schema_ref
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ArtifactSpec":
        return cls(
            artifact_id=d["artifact_id"],
            media_type=d.get("media_type"),
            schema_ref=d.get("schema_ref"),
        )


@dataclass
class RetryPolicy:
    """Timeout / retry metadata for an attempt (reserved for WP1 behavior)."""

    timeout_seconds: int | None = None
    max_attempts: int | None = None
    backoff_seconds: int | None = None

    def __post_init__(self) -> None:
        for name in ("timeout_seconds", "max_attempts", "backoff_seconds"):
            v = getattr(self, name)
            if v is not None and (not isinstance(v, int) or v < 0):
                raise TaskControllerValidationError(f"retry_policy.{name} must be int >= 0")

    def to_dict(self) -> dict:
        d: dict = {}
        for k in ("timeout_seconds", "max_attempts", "backoff_seconds"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RetryPolicy":
        return cls(
            timeout_seconds=d.get("timeout_seconds"),
            max_attempts=d.get("max_attempts"),
            backoff_seconds=d.get("backoff_seconds"),
        )


@dataclass
class EnvironmentInfo:
    """Observed/declared runtime characteristics of a host or provider."""

    os: str | None = None
    runtime: str | None = None
    arch: str | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict = {}
        for k in ("os", "runtime", "arch"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        if self.capabilities:
            d["capabilities"] = self.capabilities
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EnvironmentInfo":
        return cls(
            os=d.get("os"),
            runtime=d.get("runtime"),
            arch=d.get("arch"),
            capabilities=d.get("capabilities", []),
            metadata=d.get("metadata", {}),
        )


@dataclass
class Provenance:
    """Structured artifact provenance (no untyped dict as canonical contract)."""

    producer: str
    produced_at: str
    source_ref: str | None = None
    digest: str | None = None
    media_type: str | None = None
    schema_ref: str | None = None
    schema_version: str | None = None
    execution_ref: str | None = None
    attempt_id: str | None = None
    fencing_token: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.producer, str) or not self.producer:
            raise TaskControllerValidationError("provenance.producer must be non-empty")
        if not isinstance(self.produced_at, str) or not self.produced_at:
            raise TaskControllerValidationError("provenance.produced_at must be non-empty")

    def to_dict(self) -> dict:
        d: dict = {"producer": self.producer, "produced_at": self.produced_at}
        for k in (
            "source_ref",
            "digest",
            "media_type",
            "schema_ref",
            "schema_version",
            "execution_ref",
            "attempt_id",
            "fencing_token",
        ):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Provenance":
        return cls(
            producer=d["producer"],
            produced_at=d["produced_at"],
            source_ref=d.get("source_ref"),
            digest=d.get("digest"),
            media_type=d.get("media_type"),
            schema_ref=d.get("schema_ref"),
            schema_version=d.get("schema_version"),
            execution_ref=d.get("execution_ref"),
            attempt_id=d.get("attempt_id"),
            fencing_token=d.get("fencing_token"),
        )


@dataclass
class EventCursor:
    """Last observed event bookkeeping for reconstruct-without-chat."""

    last_event_id: str | None = None
    sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise TaskControllerValidationError("event_cursor.sequence must be int >= 0")

    def to_dict(self) -> dict:
        d: dict = {"sequence": self.sequence}
        if self.last_event_id is not None:
            d["last_event_id"] = self.last_event_id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EventCursor":
        return cls(last_event_id=d.get("last_event_id"), sequence=d.get("sequence", 0))


@dataclass
class Checkpoint:
    """Run-state checkpoint / state version slot."""

    state_version: int
    checkpoint_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state_version, int) or self.state_version < 0:
            raise TaskControllerValidationError("checkpoint.state_version must be int >= 0")

    def to_dict(self) -> dict:
        d: dict = {"state_version": self.state_version}
        if self.checkpoint_ref is not None:
            d["checkpoint_ref"] = self.checkpoint_ref
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        return cls(state_version=d["state_version"], checkpoint_ref=d.get("checkpoint_ref"))


@dataclass
class NodeState:
    """Per-node state within a run (TeamRunState reconstruction)."""

    status: str
    contract_ref: str | None = None
    current_attempt: int | None = None
    lease_ref: str | None = None
    artifact_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        from taskcontroller.domain.enums import NodeStatus

        as_enum(NodeStatus, self.status, 'status')

    def to_dict(self) -> dict:
        d: dict = {"status": self.status}
        if self.contract_ref is not None:
            d["contract_ref"] = self.contract_ref
        if self.current_attempt is not None:
            d["current_attempt"] = self.current_attempt
        if self.lease_ref is not None:
            d["lease_ref"] = self.lease_ref
        if self.artifact_refs:
            d["artifact_refs"] = self.artifact_refs
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NodeState":
        return cls(
            status=d["status"],
            contract_ref=d.get("contract_ref"),
            current_attempt=d.get("current_attempt"),
            lease_ref=d.get("lease_ref"),
            artifact_refs=d.get("artifact_refs", []),
        )
