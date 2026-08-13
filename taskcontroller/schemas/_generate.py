"""Generate the 12 WP0 model JSON Schemas from a single spec (keeps them
aligned with common.schema.json $defs). Run once to emit schema files."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON_ID = "https://dw-superapps/taskcontroller/schemas/common.schema.json"
DEF = f"{COMMON_ID}#/$defs"  # fully-qualified $defs base

# Each entry: (filename, title, required, extra_properties)
# Properties reference common $defs via $ref. We keep additionalProperties
# false per model for strictness.

SPECS = {
    "controller_host_profile": {
        "title": "ControllerHostProfile",
        "required": ["host_id", "actor_kind", "trust_tier", "environment"],
        "properties": {
            "host_id": {"$ref": f"{DEF}/Id"},
            "actor_kind": {"$ref": f"{DEF}/ActorKind"},
            "trust_tier": {"$ref": f"{DEF}/TrustTier"},
            "environment": {"$ref": f"{DEF}/EnvironmentInfo"},
            "bindings": {"type": "array", "items": {"$ref": f"{DEF}/Binding"}},
            "capabilities": {"type": "array", "items": {"$ref": f"{DEF}/CapabilityRef"}},
            "version": {"$ref": f"{DEF}/Version"},
        },
    },
    "capability_card": {
        "title": "CapabilityCard",
        "required": ["capability_id", "name", "version", "idempotency", "cost_class", "required_environment"],
        "properties": {
            "capability_id": {"$ref": f"{DEF}/Id"},
            "name": {"$ref": f"{DEF}/NonEmptyString"},
            "version": {"$ref": f"{DEF}/Version"},
            "idempotency": {"$ref": f"{DEF}/Idempotency"},
            "cost_class": {"$ref": f"{DEF}/CostClass"},
            "required_environment": {"$ref": f"{DEF}/EnvironmentRequirement"},
            "supported_binding_types": {"type": "array", "items": {"$ref": f"{DEF}/BindingType"}},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    },
    "execution_provider_card": {
        "title": "ExecutionProviderCard",
        "required": ["provider_id", "provider_kind"],
        "properties": {
            "provider_id": {"$ref": f"{DEF}/Id"},
            "provider_kind": {"$ref": f"{DEF}/ProviderKind"},
            "capability_refs": {"type": "array", "items": {"$ref": f"{DEF}/CapabilityRef"}},
            "environment": {"$ref": f"{DEF}/EnvironmentInfo"},
            "bindings": {"type": "array", "items": {"$ref": f"{DEF}/Binding"}},
            "trust_tier": {"$ref": f"{DEF}/TrustTier"},
            "cost_class": {"$ref": f"{DEF}/CostClass"},
            "capacity": {"type": "object"},
            "availability": {"type": "object"},
            "limits": {"type": "object"},
            "version": {"$ref": f"{DEF}/Version"},
        },
    },
    "task_contract": {
        "title": "TaskContract",
        "required": ["contract_id", "run_id", "node_id", "objective", "scope", "acceptance_criteria", "capability_requirement"],
        "properties": {
            "contract_id": {"$ref": f"{DEF}/Id"},
            "run_id": {"$ref": f"{DEF}/Id"},
            "node_id": {"$ref": f"{DEF}/Id"},
            "objective": {"$ref": f"{DEF}/NonEmptyString"},
            "scope": {"$ref": f"{DEF}/ScopeSpec"},
            "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "capability_requirement": {"$ref": f"{DEF}/CapabilityRequirement"},
            "dependencies": {"type": "array", "items": {"$ref": f"{DEF}/TaskRef"}},
            "required_evidence": {"type": "array", "items": {"$ref": f"{DEF}/EvidenceSpec"}},
            "reporting": {"$ref": f"{DEF}/ReportingSpec"},
            "priority": {"$ref": f"{DEF}/Priority"},
            "plan_version": {"$ref": f"{DEF}/Version"},
            "run_version": {"$ref": f"{DEF}/Version"},
        },
    },
    "execution_request": {
        "title": "ExecutionRequest",
        "required": ["execution_id", "contract_ref", "attempt", "attempt_id", "fencing_token", "capability_requirements", "environment_requirements", "routing_preferences"],
        "properties": {
            "execution_id": {"$ref": f"{DEF}/Id"},
            "contract_ref": {"$ref": f"{DEF}/NonEmptyString"},
            "attempt": {"type": "integer", "minimum": 1},
            "attempt_id": {"$ref": f"{DEF}/Id"},
            "fencing_token": {"$ref": f"{DEF}/NonEmptyString"},
            "capability_requirements": {"$ref": f"{DEF}/CapabilityRequirement"},
            "environment_requirements": {"$ref": f"{DEF}/EnvironmentRequirement"},
            "routing_preferences": {"$ref": f"{DEF}/RoutingPref"},
            "inputs": {"type": "array", "items": {"$ref": f"{DEF}/InputRef"}},
            "permissions": {"$ref": f"{DEF}/Permission"},
            "expected_outputs": {"type": "array", "items": {"$ref": f"{DEF}/ArtifactSpec"}},
            "retry": {"$ref": f"{DEF}/RetryPolicy"},
            "plan_version": {"$ref": f"{DEF}/Version"},
            "run_version": {"$ref": f"{DEF}/Version"},
        },
    },
    "execution_receipt": {
        "title": "ExecutionReceipt",
        "required": ["receipt_id", "contract_ref", "execution_ref", "selected_provider", "status"],
        "properties": {
            "receipt_id": {"$ref": f"{DEF}/Id"},
            "contract_ref": {"$ref": f"{DEF}/NonEmptyString"},
            "execution_ref": {"$ref": f"{DEF}/ExecutionRef"},
            "selected_provider": {"$ref": f"{DEF}/ProviderRef"},
            "binding": {"$ref": f"{DEF}/BindingRef"},
            "status": {"$ref": f"{DEF}/ExecutionStatus"},
            "accepted_at": {"type": "string"},
        },
    },
    "agent_event": {
        "title": "AgentEvent",
        "required": ["event_id", "run_id", "node_id", "execution_id", "attempt_id", "fencing_token", "sequence", "event_type", "producer", "timestamp"],
        "properties": {
            "event_id": {"$ref": f"{DEF}/Id"},
            "run_id": {"$ref": f"{DEF}/Id"},
            "node_id": {"$ref": f"{DEF}/Id"},
            "execution_id": {"$ref": f"{DEF}/Id"},
            "attempt_id": {"$ref": f"{DEF}/Id"},
            "fencing_token": {"$ref": f"{DEF}/NonEmptyString"},
            "sequence": {"type": "integer", "minimum": 0},
            "event_type": {"$ref": f"{DEF}/EventType"},
            "producer": {"$ref": f"{DEF}/ProducerRef"},
            "timestamp": {"$ref": f"{DEF}/NonEmptyString"},
            "idempotency_key": {"type": "string"},
            "payload": {"type": "object"},
            "artifact_refs": {"type": "array", "items": {"$ref": f"{DEF}/ArtifactRef"}},
        },
    },
    "artifact": {
        "title": "Artifact",
        "required": ["artifact_id", "content_ref", "media_type", "provenance"],
        "properties": {
            "artifact_id": {"$ref": f"{DEF}/Id"},
            "content_ref": {"$ref": f"{DEF}/NonEmptyString"},
            "media_type": {"$ref": f"{DEF}/NonEmptyString"},
            "provenance": {"$ref": f"{DEF}/Provenance"},
            "digest": {"type": "string"},
            "schema_ref": {"type": "string"},
            "schema_version": {"type": "string"},
        },
    },
    "review_result": {
        "title": "ReviewResult",
        "required": ["review_id", "target_ref", "verdict", "reviewer"],
        "properties": {
            "review_id": {"$ref": f"{DEF}/Id"},
            "target_ref": {"$ref": f"{DEF}/NonEmptyString"},
            "verdict": {"$ref": f"{DEF}/ReviewVerdict"},
            "reviewer": {"$ref": f"{DEF}/NonEmptyString"},
            "criteria": {"type": "array", "items": {"type": "string"}},
            "score": {"type": "number"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "plan_version": {"$ref": f"{DEF}/Version"},
            "run_version": {"$ref": f"{DEF}/Version"},
        },
    },
    "work_lease": {
        "title": "WorkLease",
        "required": ["lease_id", "run_id", "node_id", "execution_id", "attempt_id", "holder", "fencing_token", "granted_at", "expires_at", "status"],
        "properties": {
            "lease_id": {"$ref": f"{DEF}/Id"},
            "run_id": {"$ref": f"{DEF}/Id"},
            "node_id": {"$ref": f"{DEF}/Id"},
            "execution_id": {"$ref": f"{DEF}/Id"},
            "attempt_id": {"$ref": f"{DEF}/Id"},
            "holder": {"$ref": f"{DEF}/ProviderRef"},
            "fencing_token": {"$ref": f"{DEF}/NonEmptyString"},
            "granted_at": {"$ref": f"{DEF}/NonEmptyString"},
            "expires_at": {"$ref": f"{DEF}/NonEmptyString"},
            "resource_ref": {"type": "string"},
            "status": {"$ref": f"{DEF}/LeaseStatus"},
        },
    },
    "team_run_state": {
        "title": "TeamRunState",
        "required": ["run_id", "status", "nodes", "active_attempts", "active_leases", "artifact_refs"],
        "properties": {
            "run_id": {"$ref": f"{DEF}/Id"},
            "status": {"$ref": f"{DEF}/RunStatus"},
            "nodes": {"type": "object", "additionalProperties": {"$ref": f"{DEF}/NodeState"}},
            "active_attempts": {"type": "array", "items": {"type": "string"}},
            "active_leases": {"type": "array", "items": {"type": "string"}},
            "artifact_refs": {"type": "array", "items": {"type": "string"}},
            "last_event_cursor": {"$ref": f"{DEF}/EventCursor"},
            "checkpoint": {"$ref": f"{DEF}/Checkpoint"},
            "plan_version": {"$ref": f"{DEF}/Version"},
            "run_version": {"$ref": f"{DEF}/Version"},
            "updated_at": {"type": "string"},
        },
    },
    "controller_decision": {
        "title": "ControllerDecision",
        "required": ["decision_id", "run_ref", "decision_type", "rationale", "evidence_refs"],
        "properties": {
            "decision_id": {"$ref": f"{DEF}/Id"},
            "run_ref": {"$ref": f"{DEF}/NonEmptyString"},
            "decision_type": {"$ref": f"{DEF}/DecisionType"},
            "rationale": {"$ref": f"{DEF}/NonEmptyString"},
            "selected_option": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "plan_version": {"$ref": f"{DEF}/Version"},
            "run_version": {"$ref": f"{DEF}/Version"},
        },
    },
}


def build(name: str, spec: dict) -> dict:
    schema_id = f"https://dw-superapps/taskcontroller/schemas/{name}.schema.json"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        "title": spec["title"],
        "type": "object",
        "additionalProperties": False,
        "required": spec["required"],
        "properties": spec["properties"],
    }


def main() -> None:
    for name, spec in SPECS.items():
        schema = build(name, spec)
        out = HERE / f"{name}.schema.json"
        out.write_text(json.dumps(schema, indent=2) + "\n")
        print("wrote", out.name)


if __name__ == "__main__":
    main()
