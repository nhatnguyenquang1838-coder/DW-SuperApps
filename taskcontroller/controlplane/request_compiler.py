"""Pure Controller-side compiler for one bounded mailbox/v2 request.

The compiler is deliberately a preparation boundary only. It does not select a
provider, persist a continuation, write a mailbox, emit a wakeup, or invoke an
executor. All identity, authority, and source/standards bindings are supplied by
the Controller and copied into one validated ``execution_request`` envelope.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, NoReturn, Sequence

from taskcontroller.domain.values import ScopeSpec
from taskcontroller.controlplane.execution_boundary import (
    ExecutionBoundary,
    MAX_TIME_BUDGET_SECONDS,
    MAX_TOKEN_BUDGET,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    SOURCE_MANIFEST_VERSION,
    V2MailboxEnvelope,
    V2_PROTOCOL,
    canonical_digest,
)


_SCOPE_KEYS = (
    "allowed_actions",
    "denied_actions",
    "writable_targets",
    "source_roots",
    "max_children",
    "max_parallel",
    "max_depth",
    "replan_required_when",
    "time_budget_seconds",
    "token_budget",
)
_SCOPE_LIST_KEYS = frozenset(
    {
        "allowed_actions",
        "denied_actions",
        "writable_targets",
        "source_roots",
        "replan_required_when",
    }
)
_SCOPE_ALIASES = {
    "allowed_work": "allowed_actions",
    "forbidden_actions": "denied_actions",
}
_PAYLOAD_OWNED_KEYS = frozenset(
    {
        "objective",
        "acceptance_criteria",
        "source_refs",
        "evidence_refs",
        "environment_requirements",
        "authority_constraints",
        "contract_id",
        "source_manifest_ref",
        "standards_profile_ref",
        "recipient_capability",
        "agent_instance",
        "execution_id",
        "checkpoint_id",
    }
)


@dataclass(frozen=True)
class BoundedMailboxRequest:
    """All caller-bound values needed to compile one v2 request.

    The dataclass is an input binding, not a mutable run-state store. In
    particular, IDs, digests, lease metadata, sequence, and expiry are never
    generated here. ``scope`` and ``authority_constraints`` may be ordinary
    mappings or the existing legacy ``ScopeSpec``; the compiler emits only the
    normative v2 scope shape.
    """

    message_id: str
    run_id: str
    node_id: str
    seq: int
    correlation_id: str
    contract_id: str
    plan_version: str
    contract_digest: str
    boundary_digest: str
    source_digest: str
    source_manifest_ref: str
    objective: str
    scope: Mapping[str, Any] | ScopeSpec
    acceptance_criteria: Sequence[str]
    source_refs: Sequence[Mapping[str, Any]]
    standards_profile: Mapping[str, Any]
    recipient_capability: str
    agent_instance: str
    attempt_id: str
    attempt_number: int
    lease_generation: int
    fencing_token: str
    lease_expires_at: str
    idempotency_key: str
    evidence_refs: Sequence[str] = field(default_factory=tuple)
    environment_requirements: Mapping[str, Any] = field(default_factory=dict)
    authority_constraints: Mapping[str, Any] = field(default_factory=dict)
    standards_profile_ref: str | None = None
    producer_namespace: str = "controller"
    producer_actor_id: str = "controller"
    execution_id: str | None = None
    checkpoint_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    execution_boundary: ExecutionBoundary | Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "BoundedMailboxRequest":
        """Build an input binding from a mapping without inferring authority.

        A few descriptive aliases are accepted for callers at the Controller
        boundary. Every alias maps to an explicit field; no identity or scope
        value is synthesized.
        """

        if not isinstance(values, Mapping):
            raise MailboxV2ValidationError(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                "bounded mailbox request input must be an object",
            )
        candidate = copy.deepcopy(dict(values))
        aliases = {
            "ac": "acceptance_criteria",
            "sources": "source_refs",
            "evidence": "evidence_refs",
            "standards": "standards_profile",
            "environment": "environment_requirements",
            "authority": "authority_constraints",
            "required_capability": "recipient_capability",
            "capability": "recipient_capability",
            "boundary": "execution_boundary",
        }
        for alias, field_name in aliases.items():
            if alias in candidate:
                if field_name in candidate and candidate[field_name] != candidate[alias]:
                    raise MailboxV2ValidationError(
                        MailboxV2ErrorCode.CONTRACT_MISMATCH,
                        f"conflicting aliases for {field_name}",
                    )
                candidate.setdefault(field_name, candidate.pop(alias))
        recipient = candidate.pop("recipient", None)
        if recipient is not None:
            if not isinstance(recipient, Mapping):
                raise MailboxV2ValidationError(
                    MailboxV2ErrorCode.SCHEMA_INVALID,
                    "recipient binding must be an object",
                )
            for source_key, target_key in (
                ("capability", "recipient_capability"),
                ("agent_instance", "agent_instance"),
            ):
                if source_key in recipient:
                    if target_key in candidate and candidate[target_key] != recipient[source_key]:
                        raise MailboxV2ValidationError(
                            MailboxV2ErrorCode.CONTRACT_MISMATCH,
                            f"conflicting recipient values for {target_key}",
                        )
                    candidate.setdefault(target_key, recipient[source_key])
        return _construct_from_mapping(cls, candidate)


def _construct_from_mapping(
    cls: type[BoundedMailboxRequest], values: Mapping[str, Any]
) -> BoundedMailboxRequest:
    try:
        return cls(**dict(values))
    except TypeError as exc:
        raise MailboxV2ValidationError(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            f"bounded mailbox request input is incomplete or unsupported: {exc}",
        ) from exc


def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if isinstance(value, ScopeSpec):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be an object")
    return copy.deepcopy(dict(value))


def _execution_boundary(value: Any) -> ExecutionBoundary:
    if isinstance(value, ExecutionBoundary):
        return value
    if isinstance(value, Mapping):
        return ExecutionBoundary.from_dict(value)
    _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "execution_boundary must be an ExecutionBoundary object")
    raise AssertionError("_fail must raise")


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be non-empty")
    return value


def _string_list(value: Any, name: str, *, sort_values: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be an array")
    items = [_string(item, f"{name}[]") for item in value]
    if len(set(items)) != len(items):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must not contain duplicates")
    return sorted(items) if sort_values else items


def _normalize_scope(
    scope: Mapping[str, Any] | ScopeSpec,
    authority_constraints: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge only equal overlapping authority; never widen a task scope."""

    base = _mapping(scope, "scope")
    authority_raw = _mapping(authority_constraints, "authority_constraints")

    def canonicalize(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        boundaries = raw.get("boundaries")
        if boundaries is not None:
            if not isinstance(boundaries, Mapping):
                _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name}.boundaries must be an object")
            result.update(copy.deepcopy(dict(boundaries)))
        for key, value in raw.items():
            if key == "boundaries":
                continue
            canonical_key = _SCOPE_ALIASES.get(key, key)
            if canonical_key in result and result[canonical_key] != value:
                _fail(
                    MailboxV2ErrorCode.BOUNDARY_MISMATCH,
                    f"{name} contains conflicting values for {canonical_key}",
                )
            result[canonical_key] = copy.deepcopy(value)
        return result

    base = canonicalize(base, "scope")
    authority = canonicalize(authority_raw.get("scope", authority_raw), "authority_constraints")
    if "scope" in authority_raw and not isinstance(authority_raw["scope"], Mapping):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "authority_constraints.scope must be an object")

    unknown = (set(base) | set(authority)) - set(_SCOPE_KEYS)
    if unknown:
        _fail(
            MailboxV2ErrorCode.SCHEMA_INVALID,
            "unsupported scope fields: " + ", ".join(sorted(unknown)),
        )

    normalized: dict[str, Any] = {}
    for key in _SCOPE_KEYS:
        in_base = key in base
        in_authority = key in authority
        if in_base and in_authority:
            left = base[key]
            right = authority[key]
            if key in _SCOPE_LIST_KEYS:
                left = _string_list(left, f"scope.{key}", sort_values=True)
                right = _string_list(right, f"authority_constraints.{key}", sort_values=True)
            if left != right:
                _fail(
                    MailboxV2ErrorCode.BOUNDARY_MISMATCH,
                    f"scope and authority_constraints disagree on {key}",
                )
            normalized[key] = left
        elif in_authority:
            normalized[key] = copy.deepcopy(authority[key])
        elif in_base:
            normalized[key] = copy.deepcopy(base[key])

    # Empty denied/writable sets do not grant authority and are safe structural
    # values. Limits and positive roots/actions must be explicitly bound.
    normalized.setdefault("denied_actions", [])
    normalized.setdefault("writable_targets", [])
    for key in _SCOPE_LIST_KEYS:
        if key in normalized:
            normalized[key] = _string_list(normalized[key], f"scope.{key}", sort_values=True)
    for key in ("max_children", "max_parallel", "max_depth"):
        value = normalized.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                f"scope.{key} must be explicitly bound as an integer",
            )
    for key, maximum in (
        ("time_budget_seconds", MAX_TIME_BUDGET_SECONDS),
        ("token_budget", MAX_TOKEN_BUDGET),
    ):
        value = normalized.get(key)
        if value is None:
            normalized[key] = None
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= maximum
        ):
            _fail(
                MailboxV2ErrorCode.SCHEMA_INVALID,
                f"scope.{key} must be None or an integer between 1 and {maximum}",
            )
    return normalized, authority_raw


def _normalize_source_refs(source_refs: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(source_refs, (list, tuple)) or not source_refs:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "source_refs must contain at least one source")
    sources: list[dict[str, Any]] = []
    for index, source in enumerate(source_refs):
        source_dict = _mapping(source, f"source_refs[{index}]")
        for key in ("repository", "commit_sha", "path", "blob_digest"):
            _string(source_dict.get(key), f"source_refs[{index}].{key}")
        sources.append(source_dict)
    sources.sort(
        key=lambda item: (
            item["repository"],
            item["commit_sha"],
            item["path"],
            item["blob_digest"],
        )
    )
    if len({tuple(sorted(source.items())) for source in sources}) != len(sources):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "source_refs must not contain duplicates")
    refs = [f"{item['repository']}@{item['commit_sha']}:{item['path']}" for item in sources]
    return sources, refs


def _normalize_standards_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _mapping(profile, "standards_profile")
    for key in ("profile_id", "version", "digest"):
        _string(normalized.get(key), f"standards_profile.{key}")
    return normalized


def _normalize_criteria(criteria: Sequence[str]) -> list[str]:
    if not isinstance(criteria, (list, tuple)) or not criteria:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "acceptance_criteria must contain at least one item")
    return [_string(item, "acceptance_criteria[]") for item in criteria]


def compile_bounded_mailbox_request(
    bound: BoundedMailboxRequest | Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> V2MailboxEnvelope:
    """Compile and validate one immutable v2 ``execution_request`` envelope.

    The operation is pure: repeated calls with the same bound values return
    byte-equivalent envelopes. The only calculated field is the envelope's
    top-level digest, calculated after all caller-bound values are materialized.
    """

    if bound is None:
        bound = BoundedMailboxRequest.from_mapping(kwargs)
    elif kwargs:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "pass bound input or keyword fields, not both")
    elif isinstance(bound, Mapping):
        bound = BoundedMailboxRequest.from_mapping(bound)
    if not isinstance(bound, BoundedMailboxRequest):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "bound input must be BoundedMailboxRequest or object")

    scope, authority_raw = _normalize_scope(bound.scope, bound.authority_constraints)
    if bound.execution_boundary is not None:
        execution_boundary = _execution_boundary(bound.execution_boundary)
        expected_scope = execution_boundary.to_dict()
        expected_scope.pop("scope_digest", None)
        if scope != expected_scope:
            _fail(
                MailboxV2ErrorCode.REPLAN_REQUIRED,
                "compiled scope does not exactly bind execution_boundary",
            )
        if bound.boundary_digest != execution_boundary.digest():
            _fail(
                MailboxV2ErrorCode.BOUNDARY_MISMATCH,
                "boundary_digest does not match execution_boundary",
            )
    sources, source_ref_strings = _normalize_source_refs(bound.source_refs)
    criteria = _normalize_criteria(bound.acceptance_criteria)
    evidence_refs = _string_list(bound.evidence_refs, "evidence_refs", sort_values=True)
    environment = _mapping(bound.environment_requirements, "environment_requirements")
    standards = _normalize_standards_profile(bound.standards_profile)
    standards_ref = bound.standards_profile_ref
    if standards_ref is None:
        version = standards["version"]
        suffix = version if version.startswith("v") else f"v{version}"
        standards_ref = f"{standards['profile_id']}/{suffix}"
    _string(standards_ref, "standards_profile_ref")

    _string(bound.message_id, "message_id")
    _string(bound.run_id, "run_id")
    _string(bound.node_id, "node_id")
    _string(bound.correlation_id, "correlation_id")
    _string(bound.contract_id, "contract_id")
    _string(bound.plan_version, "plan_version")
    _string(bound.contract_digest, "contract_digest")
    _string(bound.boundary_digest, "boundary_digest")
    _string(bound.source_digest, "source_digest")
    _string(bound.source_manifest_ref, "source_manifest_ref")
    _string(bound.objective, "objective")
    _string(bound.recipient_capability, "recipient_capability")
    _string(bound.agent_instance, "agent_instance")
    _string(bound.attempt_id, "attempt_id")
    _string(bound.fencing_token, "fencing_token")
    _string(bound.lease_expires_at, "lease_expires_at")
    _string(bound.idempotency_key, "idempotency_key")
    _string(bound.producer_namespace, "producer_namespace")
    _string(bound.producer_actor_id, "producer_actor_id")
    if not isinstance(bound.seq, int) or isinstance(bound.seq, bool) or bound.seq < 0:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "seq must be int >= 0")
    if not isinstance(bound.attempt_number, int) or isinstance(bound.attempt_number, bool) or bound.attempt_number < 1:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "attempt_number must be int >= 1")
    if not isinstance(bound.lease_generation, int) or isinstance(bound.lease_generation, bool) or bound.lease_generation < 0:
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "lease_generation must be int >= 0")

    extra_payload = _mapping(bound.payload, "payload")
    collision = _PAYLOAD_OWNED_KEYS.intersection(extra_payload)
    if collision:
        _fail(
            MailboxV2ErrorCode.CONTRACT_MISMATCH,
            "payload cannot override compiler-owned fields: " + ", ".join(sorted(collision)),
        )
    request_payload = copy.deepcopy(extra_payload)
    request_payload.update(
        {
            "objective": bound.objective,
            "acceptance_criteria": criteria,
            "source_refs": source_ref_strings,
            "evidence_refs": evidence_refs,
            "environment_requirements": environment,
            "authority_constraints": authority_raw,
            "contract_id": bound.contract_id,
            "source_manifest_ref": bound.source_manifest_ref,
            "standards_profile_ref": standards_ref,
            "recipient_capability": bound.recipient_capability,
            "agent_instance": bound.agent_instance,
        }
    )
    if bound.execution_id is not None:
        _string(bound.execution_id, "execution_id")
        request_payload["execution_id"] = bound.execution_id
    if bound.checkpoint_id is not None:
        _string(bound.checkpoint_id, "checkpoint_id")
        request_payload["checkpoint_id"] = bound.checkpoint_id

    attempt = {
        "attempt_id": bound.attempt_id,
        "boundary_digest": bound.boundary_digest,
        "attempt_number": bound.attempt_number,
        "lease_generation": bound.lease_generation,
        "fencing_token": bound.fencing_token,
        "agent_instance": bound.agent_instance,
        "lease_expires_at": bound.lease_expires_at,
    }
    logical_contract = {
        "contract_id": bound.contract_id,
        "plan_version": bound.plan_version,
        "contract_digest": bound.contract_digest,
        "boundary_digest": bound.boundary_digest,
        "source_digest": bound.source_digest,
        "objective": bound.objective,
        "scope": scope,
        "acceptance_criteria": criteria,
        "standards_profile_ref": standards_ref,
        "source_manifest_ref": bound.source_manifest_ref,
    }
    candidate: dict[str, Any] = {
        "protocol": V2_PROTOCOL,
        "message_id": bound.message_id,
        "run_id": bound.run_id,
        "node_id": bound.node_id,
        "seq": bound.seq,
        "correlation_id": bound.correlation_id,
        "direction": "controller_to_executor",
        "message_type": "execution_request",
        "producer": {
            "namespace": bound.producer_namespace,
            "actor_id": bound.producer_actor_id,
            "role": "controller",
        },
        "recipient": {
            "capability": bound.recipient_capability,
            "agent_instance": bound.agent_instance,
        },
        "logical_contract": logical_contract,
        "attempt": attempt,
        "execution_identity": {
            "run_id": bound.run_id,
            "node_id": bound.node_id,
            "plan_version": bound.plan_version,
            "contract_digest": bound.contract_digest,
            "boundary_digest": bound.boundary_digest,
            "source_digest": bound.source_digest,
            "attempt_id": bound.attempt_id,
            "lease_generation": bound.lease_generation,
            "fencing_token": bound.fencing_token,
        },
        "source_manifest": {
            "manifest_version": SOURCE_MANIFEST_VERSION,
            "digest": bound.source_digest,
            "sources": sources,
        },
        "standards_profile": standards,
        "payload": request_payload,
        "provenance": {
            "origin": "controller",
            "parent_message_id": None,
            "child_id": None,
            "lens": None,
            "agent_instance": bound.agent_instance,
            "status": "REQUESTED",
            "source_refs": source_ref_strings,
            "evidence_refs": evidence_refs,
            "result_digest": None,
        },
        "result": None,
        "idempotency_key": bound.idempotency_key,
    }
    candidate["digest"] = canonical_digest(candidate)
    return V2MailboxEnvelope.from_dict(candidate)


# Descriptive aliases make the pure operation discoverable without introducing
# a second implementation or a second protocol surface.
compile_bounded_request = compile_bounded_mailbox_request
compile_execution_request = compile_bounded_mailbox_request
RequestCompilationInput = BoundedMailboxRequest
MailboxRequestCompiler = compile_bounded_mailbox_request


__all__ = [
    "BoundedMailboxRequest",
    "MailboxRequestCompiler",
    "RequestCompilationInput",
    "compile_bounded_mailbox_request",
    "compile_bounded_request",
    "compile_execution_request",
]
