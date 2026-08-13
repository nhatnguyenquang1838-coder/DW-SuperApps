"""WP0 TaskController canonical domain models (framework-neutral dataclasses).

These are the Python MVP. The canonical, language-neutral contract lives in
``taskcontroller/schemas/*.schema.json`` (JSON Schema draft 2020-12). Every
model here is (de)serializable via the helpers in ``serialization.py`` and is
validatable against its JSON Schema via ``taskcontroller.validation``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from taskcontroller.domain.enums import (
    ActorKind,
    CostClass,
    DecisionType,
    EventType,
    ExecutionStatus,
    Idempotency,
    LeaseStatus,
    NodeStatus,
    Priority,
    ProviderKind,
    ReviewVerdict,
    RunStatus,
    TrustTier,
    as_enum,
)
from taskcontroller.domain.ids import (
    _validate_id,
    ArtifactRef,
    BindingRef,
    CapabilityRef,
    ExecutionRef,
    ProducerRef,
    ProviderRef,
    TaskRef,
)
from taskcontroller.domain.values import (
    ArtifactSpec,
    Binding,
    Checkpoint,
    EnvironmentInfo,
    EnvironmentRequirement,
    EventCursor,
    EvidenceSpec,
    InputRef,
    NodeState,
    Permission,
    Provenance,
    ReportingSpec,
    RetryPolicy,
    RoutingPref,
    ScopeSpec,
    CapabilityRequirement,
)
from taskcontroller.errors import TaskControllerValidationError


def _non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise TaskControllerValidationError(f"{name} must be a non-empty string")


def _non_empty_version(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{name} must be a non-empty version string")


@dataclass
class ControllerHostProfile:
    """Runtime host (environment + bindings + capabilities). Actor role is separate."""

    host_id: str
    actor_kind: str  # ActorKind: CONTROLLER/AGENT/HUMAN/SERVICE/TOOL
    trust_tier: str  # TrustTier
    environment: EnvironmentInfo
    bindings: list[Binding] = field(default_factory=list)
    capabilities: list[CapabilityRef] = field(default_factory=list)
    version: str = "1"

    def __post_init__(self) -> None:
        _validate_id("host_id", self.host_id)
        as_enum(ActorKind, self.actor_kind, 'actor_kind')
        as_enum(TrustTier, self.trust_tier, 'trust_tier')
        _non_empty_version("version", self.version)

    def to_dict(self) -> dict:
        return {
            "host_id": self.host_id,
            "actor_kind": self.actor_kind,
            "trust_tier": self.trust_tier,
            "environment": self.environment.to_dict(),
            "bindings": [b.to_dict() for b in self.bindings],
            "capabilities": [c.to_dict() for c in self.capabilities],
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ControllerHostProfile":
        return cls(
            host_id=d["host_id"],
            actor_kind=d["actor_kind"],
            trust_tier=d["trust_tier"],
            environment=EnvironmentInfo.from_dict(d["environment"]),
            bindings=[Binding.from_dict(x) for x in d.get("bindings", [])],
            capabilities=[CapabilityRef.from_dict(x) for x in d.get("capabilities", [])],
            version=d.get("version", "1"),
        )


@dataclass
class CapabilityCard:
    """One reusable capability definition (NOT a provider-instance identity)."""

    capability_id: str
    name: str
    version: str  # semver
    idempotency: str  # Idempotency
    cost_class: str  # CostClass
    required_environment: EnvironmentRequirement
    supported_binding_types: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_id("capability_id", self.capability_id)
        _non_empty("name", self.name)
        _non_empty_version("version", self.version)
        as_enum(Idempotency, self.idempotency, 'idempotency')
        as_enum(CostClass, self.cost_class, 'cost_class')
        for bt in self.supported_binding_types:
            from taskcontroller.domain.enums import BindingType

            BindingType(bt)

    def to_dict(self) -> dict:
        d = {
            "capability_id": self.capability_id,
            "name": self.name,
            "version": self.version,
            "idempotency": self.idempotency,
            "cost_class": self.cost_class,
            "required_environment": self.required_environment.to_dict(),
        }
        if self.supported_binding_types:
            d["supported_binding_types"] = self.supported_binding_types
        if self.tags:
            d["tags"] = self.tags
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityCard":
        return cls(
            capability_id=d["capability_id"],
            name=d["name"],
            version=d["version"],
            idempotency=d["idempotency"],
            cost_class=d["cost_class"],
            required_environment=EnvironmentRequirement.from_dict(d["required_environment"]),
            supported_binding_types=d.get("supported_binding_types", []),
            tags=d.get("tags", []),
        )


@dataclass
class ExecutionProviderCard:
    """Canonical descriptor of any executable provider instance (local/connector/agent/...)."""

    provider_id: str
    provider_kind: str  # ProviderKind: LOCAL/CONNECTOR/AGENT/SERVICE/TOOL
    capability_refs: list[CapabilityRef] = field(default_factory=list)
    environment: EnvironmentInfo | None = None
    bindings: list[Binding] = field(default_factory=list)  # 0..n
    trust_tier: str | None = None  # TrustTier
    cost_class: str | None = None  # CostClass
    capacity: dict = field(default_factory=dict)  # routing metadata slot
    availability: dict | None = None  # reserved runtime snapshot
    limits: dict | None = None  # reserved runtime snapshot
    version: str = "1"

    def __post_init__(self) -> None:
        _validate_id("provider_id", self.provider_id)
        as_enum(ProviderKind, self.provider_kind, 'provider_kind')
        _non_empty_version("version", self.version)
        if self.trust_tier is not None:
            as_enum(TrustTier, self.trust_tier, 'trust_tier')
        if self.cost_class is not None:
            as_enum(CostClass, self.cost_class, 'cost_class')

    def to_dict(self) -> dict:
        d: dict = {
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "capability_refs": [c.to_dict() for c in self.capability_refs],
            "bindings": [b.to_dict() for b in self.bindings],
            "version": self.version,
        }
        if self.environment is not None:
            d["environment"] = self.environment.to_dict()
        if self.trust_tier is not None:
            d["trust_tier"] = self.trust_tier
        if self.cost_class is not None:
            d["cost_class"] = self.cost_class
        if self.capacity:
            d["capacity"] = self.capacity
        if self.availability is not None:
            d["availability"] = self.availability
        if self.limits is not None:
            d["limits"] = self.limits
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionProviderCard":
        return cls(
            provider_id=d["provider_id"],
            provider_kind=d["provider_kind"],
            capability_refs=[CapabilityRef.from_dict(x) for x in d.get("capability_refs", [])],
            environment=EnvironmentInfo.from_dict(d["environment"]) if d.get("environment") else None,
            bindings=[Binding.from_dict(x) for x in d.get("bindings", [])],
            trust_tier=d.get("trust_tier"),
            cost_class=d.get("cost_class"),
            capacity=d.get("capacity", {}),
            availability=d.get("availability"),
            limits=d.get("limits"),
            version=d.get("version", "1"),
        )


@dataclass
class TaskContract:
    """Bounded logical work contract (distinct from per-attempt ExecutionRequest)."""

    contract_id: str
    run_id: str
    node_id: str
    objective: str
    scope: ScopeSpec
    acceptance_criteria: list[str]
    capability_requirement: CapabilityRequirement
    dependencies: list[TaskRef] = field(default_factory=list)
    required_evidence: list[EvidenceSpec] = field(default_factory=list)
    reporting: ReportingSpec | None = None
    priority: str = "MEDIUM"  # Priority
    plan_version: str = ""
    run_version: str = ""

    def __post_init__(self) -> None:
        _validate_id("contract_id", self.contract_id)
        _validate_id("run_id", self.run_id)
        _validate_id("node_id", self.node_id)
        _non_empty("objective", self.objective)
        if not self.acceptance_criteria:
            raise TaskControllerValidationError("task_contract.acceptance_criteria must be non-empty")
        as_enum(Priority, self.priority, 'priority')
        # reject self-dependency (node cannot depend on itself)
        for dep in self.dependencies:
            if dep.run_id == self.run_id and dep.node_id == self.node_id:
                raise TaskControllerValidationError("task_contract must not self-depend")

    def to_dict(self) -> dict:
        d: dict = {
            "contract_id": self.contract_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "objective": self.objective,
            "scope": self.scope.to_dict(),
            "acceptance_criteria": self.acceptance_criteria,
            "capability_requirement": self.capability_requirement.to_dict(),
            "dependencies": [x.to_dict() for x in self.dependencies],
            "required_evidence": [x.to_dict() for x in self.required_evidence],
            "priority": self.priority,
            "plan_version": self.plan_version,
            "run_version": self.run_version,
        }
        if self.reporting is not None:
            d["reporting"] = self.reporting.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TaskContract":
        return cls(
            contract_id=d["contract_id"],
            run_id=d["run_id"],
            node_id=d["node_id"],
            objective=d["objective"],
            scope=ScopeSpec.from_dict(d["scope"]),
            acceptance_criteria=d["acceptance_criteria"],
            capability_requirement=CapabilityRequirement.from_dict(d["capability_requirement"]),
            dependencies=[TaskRef.from_dict(x) for x in d.get("dependencies", [])],
            required_evidence=[EvidenceSpec.from_dict(x) for x in d.get("required_evidence", [])],
            reporting=ReportingSpec.from_dict(d["reporting"]) if d.get("reporting") else None,
            priority=d.get("priority", "MEDIUM"),
            plan_version=d.get("plan_version", ""),
            run_version=d.get("run_version", ""),
        )


@dataclass
class ExecutionRequest:
    """Compiles ONE concrete attempt from a TaskContract (no permanent host binding)."""

    execution_id: str
    contract_ref: str
    attempt: int
    attempt_id: str
    fencing_token: str
    capability_requirements: CapabilityRequirement
    environment_requirements: EnvironmentRequirement
    routing_preferences: RoutingPref
    inputs: list[InputRef] = field(default_factory=list)
    permissions: Permission | None = None
    expected_outputs: list[ArtifactSpec] = field(default_factory=list)
    retry: RetryPolicy | None = None
    plan_version: str = ""
    run_version: str = ""

    def __post_init__(self) -> None:
        _validate_id("execution_id", self.execution_id)
        _validate_id("contract_ref", self.contract_ref)
        _validate_id("attempt_id", self.attempt_id)
        _non_empty("fencing_token", self.fencing_token)
        if not isinstance(self.attempt, int) or self.attempt < 1:
            raise TaskControllerValidationError("execution_request.attempt must be int >= 1")

    def to_dict(self) -> dict:
        d: dict = {
            "execution_id": self.execution_id,
            "contract_ref": self.contract_ref,
            "attempt": self.attempt,
            "attempt_id": self.attempt_id,
            "fencing_token": self.fencing_token,
            "capability_requirements": self.capability_requirements.to_dict(),
            "environment_requirements": self.environment_requirements.to_dict(),
            "routing_preferences": self.routing_preferences.to_dict(),
            "inputs": [x.to_dict() for x in self.inputs],
            "expected_outputs": [x.to_dict() for x in self.expected_outputs],
            "plan_version": self.plan_version,
            "run_version": self.run_version,
        }
        if self.permissions is not None:
            d["permissions"] = self.permissions.to_dict()
        if self.retry is not None:
            d["retry"] = self.retry.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionRequest":
        return cls(
            execution_id=d["execution_id"],
            contract_ref=d["contract_ref"],
            attempt=d["attempt"],
            attempt_id=d["attempt_id"],
            fencing_token=d["fencing_token"],
            capability_requirements=CapabilityRequirement.from_dict(d["capability_requirements"]),
            environment_requirements=EnvironmentRequirement.from_dict(d["environment_requirements"]),
            routing_preferences=RoutingPref.from_dict(d["routing_preferences"]),
            inputs=[InputRef.from_dict(x) for x in d.get("inputs", [])],
            permissions=Permission.from_dict(d["permissions"]) if d.get("permissions") else None,
            expected_outputs=[ArtifactSpec.from_dict(x) for x in d.get("expected_outputs", [])],
            retry=RetryPolicy.from_dict(d["retry"]) if d.get("retry") else None,
            plan_version=d.get("plan_version", ""),
            run_version=d.get("run_version", ""),
        )


@dataclass
class ExecutionReceipt:
    """Accepted assignment: selected provider + binding + attempt correlation."""

    receipt_id: str
    contract_ref: str
    execution_ref: ExecutionRef
    selected_provider: ProviderRef  # generic, NOT AgentInstanceRef
    binding: BindingRef | None
    status: str  # ExecutionStatus
    accepted_at: str | None = None

    def __post_init__(self) -> None:
        _validate_id("receipt_id", self.receipt_id)
        _validate_id("contract_ref", self.contract_ref)
        as_enum(ExecutionStatus, self.status, 'status')

    def to_dict(self) -> dict:
        d: dict = {
            "receipt_id": self.receipt_id,
            "contract_ref": self.contract_ref,
            "execution_ref": self.execution_ref.to_dict(),
            "selected_provider": self.selected_provider.to_dict(),
            "status": self.status,
        }
        if self.binding is not None:
            d["binding"] = self.binding.to_dict()
        if self.accepted_at is not None:
            d["accepted_at"] = self.accepted_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionReceipt":
        return cls(
            receipt_id=d["receipt_id"],
            contract_ref=d["contract_ref"],
            execution_ref=ExecutionRef.from_dict(d["execution_ref"]),
            selected_provider=ProviderRef.from_dict(d["selected_provider"]),
            binding=BindingRef.from_dict(d["binding"]) if d.get("binding") else None,
            status=d["status"],
            accepted_at=d.get("accepted_at"),
        )


@dataclass
class AgentEvent:
    """Canonical correlated event; monotonic sequence + idempotency for stale/late rejection."""

    event_id: str
    run_id: str
    node_id: str
    execution_id: str
    attempt_id: str
    fencing_token: str
    sequence: int
    event_type: str  # EventType
    producer: ProducerRef
    timestamp: str
    idempotency_key: str | None = None
    payload: dict | None = None
    artifact_refs: list[ArtifactRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_id("event_id", self.event_id)
        _validate_id("run_id", self.run_id)
        _validate_id("node_id", self.node_id)
        _validate_id("execution_id", self.execution_id)
        _validate_id("attempt_id", self.attempt_id)
        _non_empty("fencing_token", self.fencing_token)
        _non_empty("timestamp", self.timestamp)
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise TaskControllerValidationError("agent_event.sequence must be int >= 0")
        as_enum(EventType, self.event_type, 'event_type')

    def to_dict(self) -> dict:
        d: dict = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "execution_id": self.execution_id,
            "attempt_id": self.attempt_id,
            "fencing_token": self.fencing_token,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "producer": self.producer.to_dict(),
            "timestamp": self.timestamp,
            "artifact_refs": [a.to_dict() for a in self.artifact_refs],
        }
        if self.idempotency_key is not None:
            d["idempotency_key"] = self.idempotency_key
        if self.payload is not None:
            d["payload"] = self.payload
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AgentEvent":
        return cls(
            event_id=d["event_id"],
            run_id=d["run_id"],
            node_id=d["node_id"],
            execution_id=d["execution_id"],
            attempt_id=d["attempt_id"],
            fencing_token=d["fencing_token"],
            sequence=d["sequence"],
            event_type=d["event_type"],
            producer=ProducerRef.from_dict(d["producer"]),
            timestamp=d["timestamp"],
            idempotency_key=d.get("idempotency_key"),
            payload=d.get("payload"),
            artifact_refs=[ArtifactRef.from_dict(x) for x in d.get("artifact_refs", [])],
        )


@dataclass
class Artifact:
    """Produced artifact with structured provenance (no untyped dict)."""

    artifact_id: str
    content_ref: str
    media_type: str
    provenance: Provenance
    digest: str | None = None
    schema_ref: str | None = None
    schema_version: str | None = None

    def __post_init__(self) -> None:
        _validate_id("artifact_id", self.artifact_id)
        _non_empty("content_ref", self.content_ref)
        _non_empty("media_type", self.media_type)

    def to_dict(self) -> dict:
        d: dict = {
            "artifact_id": self.artifact_id,
            "content_ref": self.content_ref,
            "media_type": self.media_type,
            "provenance": self.provenance.to_dict(),
        }
        if self.digest is not None:
            d["digest"] = self.digest
        if self.schema_ref is not None:
            d["schema_ref"] = self.schema_ref
        if self.schema_version is not None:
            d["schema_version"] = self.schema_version
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Artifact":
        return cls(
            artifact_id=d["artifact_id"],
            content_ref=d["content_ref"],
            media_type=d["media_type"],
            provenance=Provenance.from_dict(d["provenance"]),
            digest=d.get("digest"),
            schema_ref=d.get("schema_ref"),
            schema_version=d.get("schema_version"),
        )


@dataclass
class ReviewResult:
    """Review verdict with evidence refs."""

    review_id: str
    target_ref: str
    verdict: str  # ReviewVerdict
    reviewer: str
    criteria: list[str] = field(default_factory=list)
    score: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    plan_version: str = ""
    run_version: str = ""

    def __post_init__(self) -> None:
        _validate_id("review_id", self.review_id)
        _non_empty("target_ref", self.target_ref)
        _non_empty("reviewer", self.reviewer)
        as_enum(ReviewVerdict, self.verdict, 'verdict')
        if self.score is not None and not isinstance(self.score, (int, float)):
            raise TaskControllerValidationError("review_result.score must be numeric")

    def to_dict(self) -> dict:
        d: dict = {
            "review_id": self.review_id,
            "target_ref": self.target_ref,
            "verdict": self.verdict,
            "reviewer": self.reviewer,
            "criteria": self.criteria,
            "evidence_refs": self.evidence_refs,
            "plan_version": self.plan_version,
            "run_version": self.run_version,
        }
        if self.score is not None:
            d["score"] = self.score
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewResult":
        return cls(
            review_id=d["review_id"],
            target_ref=d["target_ref"],
            verdict=d["verdict"],
            reviewer=d["reviewer"],
            criteria=d.get("criteria", []),
            score=d.get("score"),
            evidence_refs=d.get("evidence_refs", []),
            plan_version=d.get("plan_version", ""),
            run_version=d.get("run_version", ""),
        )


@dataclass
class WorkLease:
    """Binds run/node/attempt/holder/fencing-token/expiry/status."""

    lease_id: str
    run_id: str
    node_id: str
    execution_id: str
    attempt_id: str
    holder: ProviderRef  # generic provider instance
    fencing_token: str
    granted_at: str
    expires_at: str
    resource_ref: str | None = None
    status: str = "ACTIVE"  # LeaseStatus

    def __post_init__(self) -> None:
        _validate_id("lease_id", self.lease_id)
        _validate_id("run_id", self.run_id)
        _validate_id("node_id", self.node_id)
        _validate_id("execution_id", self.execution_id)
        _validate_id("attempt_id", self.attempt_id)
        _non_empty("fencing_token", self.fencing_token)
        _non_empty("granted_at", self.granted_at)
        _non_empty("expires_at", self.expires_at)
        as_enum(LeaseStatus, self.status, 'status')

    def to_dict(self) -> dict:
        d: dict = {
            "lease_id": self.lease_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "execution_id": self.execution_id,
            "attempt_id": self.attempt_id,
            "holder": self.holder.to_dict(),
            "fencing_token": self.fencing_token,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }
        if self.resource_ref is not None:
            d["resource_ref"] = self.resource_ref
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorkLease":
        return cls(
            lease_id=d["lease_id"],
            run_id=d["run_id"],
            node_id=d["node_id"],
            execution_id=d["execution_id"],
            attempt_id=d["attempt_id"],
            holder=ProviderRef.from_dict(d["holder"]),
            fencing_token=d["fencing_token"],
            granted_at=d["granted_at"],
            expires_at=d["expires_at"],
            resource_ref=d.get("resource_ref"),
            status=d.get("status", "ACTIVE"),
        )


@dataclass
class TeamRunState:
    """Sufficient to reconstruct a run without chat history."""

    run_id: str
    status: str  # RunStatus
    nodes: dict[str, NodeState] = field(default_factory=dict)
    active_attempts: list[str] = field(default_factory=list)
    active_leases: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    last_event_cursor: EventCursor | None = None
    checkpoint: Checkpoint | None = None
    plan_version: str = ""
    run_version: str = ""
    updated_at: str | None = None

    def __post_init__(self) -> None:
        _validate_id("run_id", self.run_id)
        as_enum(RunStatus, self.status, 'status')

    def to_dict(self) -> dict:
        d: dict = {
            "run_id": self.run_id,
            "status": self.status,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "active_attempts": self.active_attempts,
            "active_leases": self.active_leases,
            "artifact_refs": self.artifact_refs,
            "plan_version": self.plan_version,
            "run_version": self.run_version,
        }
        if self.last_event_cursor is not None:
            d["last_event_cursor"] = self.last_event_cursor.to_dict()
        if self.checkpoint is not None:
            d["checkpoint"] = self.checkpoint.to_dict()
        if self.updated_at is not None:
            d["updated_at"] = self.updated_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TeamRunState":
        return cls(
            run_id=d["run_id"],
            status=d["status"],
            nodes={k: NodeState.from_dict(v) for k, v in d.get("nodes", {}).items()},
            active_attempts=d.get("active_attempts", []),
            active_leases=d.get("active_leases", []),
            artifact_refs=d.get("artifact_refs", []),
            last_event_cursor=EventCursor.from_dict(d["last_event_cursor"])
            if d.get("last_event_cursor")
            else None,
            checkpoint=Checkpoint.from_dict(d["checkpoint"]) if d.get("checkpoint") else None,
            plan_version=d.get("plan_version", ""),
            run_version=d.get("run_version", ""),
            updated_at=d.get("updated_at"),
        )


@dataclass
class ControllerDecision:
    """Controller decision with reason + evidence refs."""

    decision_id: str
    run_ref: str
    decision_type: str  # DecisionType
    rationale: str
    selected_option: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    plan_version: str = ""
    run_version: str = ""

    def __post_init__(self) -> None:
        _validate_id("decision_id", self.decision_id)
        _non_empty("run_ref", self.run_ref)
        _non_empty("rationale", self.rationale)
        as_enum(DecisionType, self.decision_type, 'decision_type')

    def to_dict(self) -> dict:
        d: dict = {
            "decision_id": self.decision_id,
            "run_ref": self.run_ref,
            "decision_type": self.decision_type,
            "rationale": self.rationale,
            "evidence_refs": self.evidence_refs,
            "plan_version": self.plan_version,
            "run_version": self.run_version,
        }
        if self.selected_option is not None:
            d["selected_option"] = self.selected_option
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ControllerDecision":
        return cls(
            decision_id=d["decision_id"],
            run_ref=d["run_ref"],
            decision_type=d["decision_type"],
            rationale=d["rationale"],
            selected_option=d.get("selected_option"),
            evidence_refs=d.get("evidence_refs", []),
            plan_version=d.get("plan_version", ""),
            run_version=d.get("run_version", ""),
        )


__all__ = [
    "ControllerHostProfile",
    "CapabilityCard",
    "ExecutionProviderCard",
    "TaskContract",
    "ExecutionRequest",
    "ExecutionReceipt",
    "AgentEvent",
    "Artifact",
    "ReviewResult",
    "WorkLease",
    "TeamRunState",
    "ControllerDecision",
]
