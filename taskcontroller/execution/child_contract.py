"""TC-MBX-503 bounded child-contract generation.

This module is a pure Controller/Analyzer planning seam.  It turns one
explicit parent contract and one or more explicit child proposals into
immutable, digest-bound child contracts.  It does not persist, dispatch,
invoke providers, or enable fan-out at runtime.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn, TypeAlias

from taskcontroller.controlplane.execution_boundary import (
    BoundarySubsetProof,
    ExecutionBoundary,
    ExecutionBoundaryValidationError,
    REPLAN_REQUIRED,
)
from taskcontroller.interaction.mailbox_v2 import (
    SOURCE_MANIFEST_VERSION,
    V2MailboxEnvelope,
    canonical_bytes as mailbox_canonical_bytes,
    canonical_digest,
)
from taskcontroller.standards.resolver import StandardsProfile, StandardsSourceRef


CHILD_CONTRACT_PROTOCOL = "dw.taskcontroller.child-contract/v1"
MAX_CHILD_ID_LENGTH = 128
MAX_LENS_LENGTH = 128
MAX_OBJECTIVE_LENGTH = 1024
MAX_ACCEPTANCE_CRITERIA = 64
MAX_ACCEPTANCE_CRITERION_LENGTH = 512
MAX_SOURCE_REFS = 256
_MAX_IDENTIFIER_LENGTH = 256
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

BoundaryInput: TypeAlias = ExecutionBoundary | Mapping[str, Any]
ParentInput: TypeAlias = "ParentContract | V2MailboxEnvelope | Mapping[str, Any]"


class ChildContractError(ExecutionBoundaryValidationError):
    """Stable fail-closed error for child-contract validation."""


# The plain child contract is intentionally not a mailbox/v2 envelope.  Its
# fields are an execution-planning artifact which later adapters may bind into
# a v2 child event without changing the v1 registry or wire schema.
_SERIALIZED_FIELDS = frozenset(
    {
        "protocol",
        "child_id",
        "parent_contract_id",
        "parent_contract_digest",
        "run_id",
        "node_id",
        "plan_version",
        "lens",
        "objective",
        "acceptance_criteria",
        "scope",
        "boundary_digest",
        "parent_boundary_digest",
        "boundary_subset_proof",
        "standards_profile_ref",
        "standards_profile",
        "source_manifest_ref",
        "source_digest",
        "source_manifest",
        "agent_instance",
        "child_depth",
        "digest",
    }
)
_PARENT_FIELDS = frozenset(
    {
        "run_id",
        "node_id",
        "contract_id",
        "contract_digest",
        "plan_version",
        "boundary",
        "execution_boundary",
        "boundary_digest",
        "scope",
        "logical_contract",
        "source_digest",
        "source_manifest_ref",
        "source_manifest",
        "standards_profile_ref",
        "standards_profile",
        "objective",
        "acceptance_criteria",
        "agent_instance",
        "recipient",
        "attempt",
    }
)
_PROPOSAL_FIELDS = frozenset(
    {
        "child_id",
        "lens",
        "boundary",
        "execution_boundary",
        "scope",
        "objective",
        "acceptance_criteria",
        "agent_instance",
        "child_depth",
        "standards_profile",
        "source_manifest",
    }
)


def _fail(code: str, message: str, *, failed_checks: tuple[str, ...] = ()) -> NoReturn:
    raise ChildContractError(code, message, failed_checks=failed_checks)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("SCHEMA_INVALID", f"{name} must be an object")
    return copy.deepcopy(dict(value))


def _text(value: Any, name: str, *, max_bytes: int, identifier: bool = False) -> str:
    if not isinstance(value, str):
        _fail("SCHEMA_INVALID", f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        _fail("SCHEMA_INVALID", f"{name} must be non-empty")
    if "\x00" in normalized:
        _fail("SCHEMA_INVALID", f"{name} must not contain NUL characters")
    if len(normalized.encode("utf-8")) > max_bytes:
        _fail("SCHEMA_INVALID", f"{name} exceeds {max_bytes} UTF-8 bytes")
    if identifier and not _ID_RE.fullmatch(normalized):
        _fail("SCHEMA_INVALID", f"{name} must be a stable identifier")
    return normalized


def _digest(value: Any, name: str) -> str:
    normalized = _text(value, name, max_bytes=80)
    if not _DIGEST_RE.fullmatch(normalized):
        _fail("SCHEMA_INVALID", f"{name} must be sha256:<64 lowercase hex>")
    return normalized


def _bounded_criteria(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail("SCHEMA_INVALID", f"{name} must be an array")
    if not value:
        _fail("SCHEMA_INVALID", f"{name} must contain at least one item")
    if len(value) > MAX_ACCEPTANCE_CRITERIA:
        _fail("SCHEMA_INVALID", f"{name} exceeds {MAX_ACCEPTANCE_CRITERIA} items")
    result = tuple(
        _text(
            item,
            f"{name}[{index}]",
            max_bytes=MAX_ACCEPTANCE_CRITERION_LENGTH,
        )
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        _fail("SCHEMA_INVALID", f"{name} must not contain duplicates")
    return result


def _boundary(value: BoundaryInput, name: str) -> ExecutionBoundary:
    if isinstance(value, ExecutionBoundary):
        return value
    if isinstance(value, Mapping):
        try:
            return ExecutionBoundary.from_dict(value)
        except ExecutionBoundaryValidationError:
            raise
        except (TypeError, ValueError) as exc:
            _fail("SCHEMA_INVALID", f"{name} is invalid: {exc}")
    _fail("SCHEMA_INVALID", f"{name} must be an ExecutionBoundary object")
    raise AssertionError("_fail must raise")


def _scope(boundary: ExecutionBoundary) -> dict[str, Any]:
    payload = boundary.to_dict()
    payload.pop("scope_digest", None)
    return payload


def _normalize_profile(value: Any, name: str) -> dict[str, str]:
    if isinstance(value, StandardsProfile):
        return {
            "profile_id": value.profile_id,
            "version": value.version,
            "digest": _digest(value.digest, f"{name}.digest"),
        }
    candidate = _mapping(value, name)
    if "sources" in candidate or "source_refs" in candidate:
        # A resolver-side full profile is accepted, but the child contract
        # carries the exact wire identity only; source identity is carried by
        # source_manifest below.
        try:
            profile = StandardsProfile.from_mapping(candidate)
        except Exception as exc:
            _fail("SCHEMA_INVALID", f"{name} is invalid: {exc}")
        return {
            "profile_id": profile.profile_id,
            "version": profile.version,
            "digest": _digest(profile.digest, f"{name}.digest"),
        }
    allowed = {"profile_id", "version", "digest"}
    unknown = sorted(set(candidate) - allowed)
    if unknown:
        _fail("SCHEMA_INVALID", f"unsupported {name} fields: {', '.join(unknown)}")
    missing = sorted(allowed - set(candidate))
    if missing:
        _fail("SCHEMA_INVALID", f"missing {name} fields: {', '.join(missing)}")
    return {
        "profile_id": _text(candidate["profile_id"], f"{name}.profile_id", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True),
        "version": _text(candidate["version"], f"{name}.version", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True),
        "digest": _digest(candidate["digest"], f"{name}.digest"),
    }


def _normalize_source(value: Any, name: str) -> dict[str, str]:
    if isinstance(value, StandardsSourceRef):
        return value.to_dict()
    candidate = _mapping(value, name)
    allowed = {"repository", "commit_sha", "path", "blob_digest"}
    unknown = sorted(set(candidate) - allowed)
    if unknown:
        _fail("SCHEMA_INVALID", f"unsupported {name} fields: {', '.join(unknown)}")
    missing = sorted(allowed - set(candidate))
    if missing:
        _fail("SCHEMA_INVALID", f"missing {name} fields: {', '.join(missing)}")

    repository = candidate["repository"]
    if not isinstance(repository, str) or not re.fullmatch(r"[^/\\s]+/[^/\\s]+", repository):
        _fail("SCHEMA_INVALID", f"{name}.repository must be owner/repository")
    commit_sha = candidate["commit_sha"]
    if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", commit_sha):
        _fail("SCHEMA_INVALID", f"{name}.commit_sha must be a 40- or 64-hex commit")
    path = candidate["path"]
    if not isinstance(path, str) or not path or path.startswith("/") or "\\x00" in path or ".." in path.split("/"):
        _fail("SCHEMA_INVALID", f"{name}.path must be a relative repository path")
    blob_digest = candidate["blob_digest"]
    if not isinstance(blob_digest, str) or not _DIGEST_RE.fullmatch(blob_digest):
        _fail("SCHEMA_INVALID", f"{name}.blob_digest must be sha256 hex")
    return {
        "repository": repository,
        "commit_sha": commit_sha,
        "path": path,
        "blob_digest": blob_digest,
    }


def _normalize_manifest(value: Any, name: str) -> dict[str, Any]:
    candidate = _mapping(value, name)
    allowed = {"manifest_version", "digest", "sources"}
    unknown = sorted(set(candidate) - allowed)
    if unknown:
        _fail("SCHEMA_INVALID", f"unsupported {name} fields: {', '.join(unknown)}")
    missing = sorted(allowed - set(candidate))
    if missing:
        _fail("SCHEMA_INVALID", f"missing {name} fields: {', '.join(missing)}")
    version = _text(candidate["manifest_version"], f"{name}.manifest_version", max_bytes=_MAX_IDENTIFIER_LENGTH)
    if version != SOURCE_MANIFEST_VERSION:
        _fail("MANIFEST_VERSION_MISMATCH", f"expected {SOURCE_MANIFEST_VERSION}")
    manifest_digest = _digest(candidate["digest"], f"{name}.digest")
    sources_value = candidate["sources"]
    if not isinstance(sources_value, (list, tuple)) or not sources_value:
        _fail("SCHEMA_INVALID", f"{name}.sources must contain at least one item")
    if len(sources_value) > MAX_SOURCE_REFS:
        _fail("SCHEMA_INVALID", f"{name}.sources exceeds {MAX_SOURCE_REFS} items")
    sources = [_normalize_source(item, f"{name}.sources[{index}]") for index, item in enumerate(sources_value)]
    sources.sort(key=lambda item: (item["repository"], item["commit_sha"], item["path"], item["blob_digest"]))
    identities = [(item["repository"], item["commit_sha"], item["path"]) for item in sources]
    if len(set(identities)) != len(identities):
        _fail("SCHEMA_INVALID", f"{name}.sources must not contain duplicate identities")
    return {
        "manifest_version": version,
        "digest": manifest_digest,
        "sources": sources,
    }


def _normalize_optional_agent(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name, max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True)


def _alias(candidate: dict[str, Any], alias: str, canonical: str) -> None:
    if alias not in candidate:
        return
    if canonical in candidate and candidate[canonical] != candidate[alias]:
        _fail("CONTRACT_MISMATCH", f"conflicting values for {canonical}")
    candidate[canonical] = candidate.pop(alias)


@dataclass(frozen=True, slots=True)
class ChildContractInput:
    """Explicit, non-persisted child proposal supplied by the Controller."""

    child_id: str
    lens: str
    boundary: BoundaryInput
    objective: str | None = None
    acceptance_criteria: Sequence[str] | None = None
    agent_instance: str | None = None
    child_depth: int = 0
    standards_profile: Mapping[str, Any] | StandardsProfile | None = None
    source_manifest: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "child_id",
            _text(self.child_id, "child_id", max_bytes=MAX_CHILD_ID_LENGTH, identifier=True),
        )
        object.__setattr__(
            self,
            "lens",
            _text(self.lens, "lens", max_bytes=MAX_LENS_LENGTH, identifier=True),
        )
        object.__setattr__(self, "boundary", _boundary(self.boundary, "child boundary"))
        if self.objective is not None:
            object.__setattr__(
                self,
                "objective",
                _text(self.objective, "objective", max_bytes=MAX_OBJECTIVE_LENGTH),
            )
        if self.acceptance_criteria is not None:
            object.__setattr__(
                self,
                "acceptance_criteria",
                _bounded_criteria(self.acceptance_criteria, "acceptance_criteria"),
            )
        object.__setattr__(
            self,
            "agent_instance",
            _normalize_optional_agent(self.agent_instance, "agent_instance"),
        )
        if isinstance(self.child_depth, bool) or not isinstance(self.child_depth, int) or self.child_depth < 0:
            _fail("SCHEMA_INVALID", "child_depth must be an integer >= 0")
        if self.standards_profile is not None:
            object.__setattr__(self, "standards_profile", copy.deepcopy(self.standards_profile))
        if self.source_manifest is not None:
            if not isinstance(self.source_manifest, Mapping):
                _fail("SCHEMA_INVALID", "source_manifest must be an object")
            object.__setattr__(self, "source_manifest", copy.deepcopy(dict(self.source_manifest)))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ChildContractInput":
        if not isinstance(payload, Mapping):
            _fail("SCHEMA_INVALID", "child proposal must be an object")
        candidate = copy.deepcopy(dict(payload))
        _alias(candidate, "execution_boundary", "boundary")
        _alias(candidate, "scope", "boundary")
        unknown = sorted(set(candidate) - _PROPOSAL_FIELDS)
        if unknown:
            _fail("SCHEMA_INVALID", f"unsupported child proposal fields: {', '.join(unknown)}")
        missing = sorted({"child_id", "lens", "boundary"} - set(candidate))
        if missing:
            _fail("SCHEMA_INVALID", f"missing child proposal fields: {', '.join(missing)}")
        try:
            return cls(**candidate)
        except TypeError as exc:
            _fail("SCHEMA_INVALID", f"child proposal is incomplete: {exc}")
        raise AssertionError("_fail must raise")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "child_id": self.child_id,
            "lens": self.lens,
            "boundary": self.boundary.to_dict(),
            "objective": self.objective,
            "acceptance_criteria": (
                list(self.acceptance_criteria) if self.acceptance_criteria is not None else None
            ),
            "agent_instance": self.agent_instance,
            "child_depth": self.child_depth,
        }
        if self.standards_profile is not None:
            result["standards_profile"] = copy.deepcopy(dict(self.standards_profile))
        if self.source_manifest is not None:
            result["source_manifest"] = copy.deepcopy(dict(self.source_manifest))
        return result


ChildContractSpec = ChildContractInput


@dataclass(frozen=True, slots=True)
class ParentContract:
    """Validated Controller-owned logical parent contract binding."""

    run_id: str
    node_id: str
    contract_id: str
    contract_digest: str
    plan_version: str
    boundary: ExecutionBoundary
    source_digest: str
    source_manifest_ref: str
    source_manifest: Mapping[str, Any]
    standards_profile_ref: str
    standards_profile: Mapping[str, str]
    objective: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    agent_instance: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("run_id", "node_id", "contract_id", "plan_version"):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name, max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True),
            )
        object.__setattr__(self, "contract_digest", _digest(self.contract_digest, "contract_digest"))
        if not isinstance(self.boundary, ExecutionBoundary):
            object.__setattr__(self, "boundary", _boundary(self.boundary, "parent boundary"))  # type: ignore[arg-type]
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        object.__setattr__(
            self,
            "source_manifest_ref",
            _text(self.source_manifest_ref, "source_manifest_ref", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True),
        )
        manifest = _normalize_manifest(self.source_manifest, "source_manifest")
        if manifest["digest"] != self.source_digest:
            _fail("CONTRACT_MISMATCH", "source_manifest.digest does not match source_digest")
        object.__setattr__(self, "source_manifest", manifest)
        object.__setattr__(
            self,
            "standards_profile_ref",
            _text(self.standards_profile_ref, "standards_profile_ref", max_bytes=_MAX_IDENTIFIER_LENGTH),
        )
        object.__setattr__(self, "standards_profile", _normalize_profile(self.standards_profile, "standards_profile"))
        if self.objective is not None:
            object.__setattr__(self, "objective", _text(self.objective, "objective", max_bytes=MAX_OBJECTIVE_LENGTH))
        object.__setattr__(self, "acceptance_criteria", _bounded_criteria(self.acceptance_criteria, "acceptance_criteria"))
        object.__setattr__(self, "agent_instance", _normalize_optional_agent(self.agent_instance, "agent_instance"))

    @classmethod
    def from_mapping(cls, parent: ParentInput) -> "ParentContract":
        if isinstance(parent, cls):
            return parent
        if isinstance(parent, V2MailboxEnvelope):
            raw = parent.to_dict()
        elif isinstance(parent, Mapping):
            raw = copy.deepcopy(dict(parent))
        else:
            _fail("SCHEMA_INVALID", "parent contract must be an object or V2MailboxEnvelope")

        if raw.get("protocol") == "dw.taskcontroller.mailbox/v2":
            try:
                raw = V2MailboxEnvelope.from_dict(raw).to_dict()
            except Exception as exc:
                _fail("SCHEMA_INVALID", f"parent v2 envelope is invalid: {exc}")

        unknown = sorted(set(raw) - _PARENT_FIELDS - {"protocol", "message_id", "seq", "correlation_id", "direction", "message_type", "producer", "recipient", "payload", "provenance", "result", "idempotency_key", "digest", "execution_identity"})
        if unknown:
            _fail("SCHEMA_INVALID", f"unsupported parent fields: {', '.join(unknown)}")

        logical = _mapping(raw.get("logical_contract", raw), "logical_contract")
        boundary_value = raw.get("execution_boundary", raw.get("boundary"))
        if boundary_value is None:
            boundary_value = logical.get("execution_boundary", logical.get("boundary", logical.get("scope")))
        if boundary_value is None:
            _fail("SCHEMA_INVALID", "parent boundary is required and cannot be inferred")
        parent_boundary = _boundary(boundary_value, "parent boundary")
        supplied_boundary_digest = raw.get("boundary_digest", logical.get("boundary_digest"))
        if supplied_boundary_digest is not None and _digest(supplied_boundary_digest, "boundary_digest") != parent_boundary.digest():
            _fail("BOUNDARY_MISMATCH", "parent boundary_digest does not match parent boundary")

        source_manifest = raw.get("source_manifest", logical.get("source_manifest"))
        if source_manifest is None:
            _fail("SCHEMA_INVALID", "parent source_manifest is required")
        standards_profile = raw.get("standards_profile", logical.get("standards_profile"))
        if standards_profile is None:
            _fail("SCHEMA_INVALID", "parent standards_profile is required")
        recipient = raw.get("recipient")
        recipient_instance = recipient.get("agent_instance") if isinstance(recipient, Mapping) else None
        attempt = raw.get("attempt")
        attempt_instance = attempt.get("agent_instance") if isinstance(attempt, Mapping) else None
        identity = raw.get("execution_identity")
        identity_map = identity if isinstance(identity, Mapping) else {}
        agent_instance = raw.get("agent_instance", recipient_instance or attempt_instance)
        if agent_instance is None:
            agent_instance = identity_map.get("agent_instance")

        try:
            return cls(
                run_id=logical["run_id"] if "run_id" in logical else raw["run_id"],
                node_id=logical["node_id"] if "node_id" in logical else raw["node_id"],
                contract_id=logical["contract_id"],
                contract_digest=logical["contract_digest"],
                plan_version=logical["plan_version"],
                boundary=parent_boundary,
                source_digest=logical["source_digest"],
                source_manifest_ref=logical["source_manifest_ref"],
                source_manifest=source_manifest,
                standards_profile_ref=logical["standards_profile_ref"],
                standards_profile=standards_profile,
                objective=logical.get("objective"),
                acceptance_criteria=logical["acceptance_criteria"],
                agent_instance=agent_instance,
            )
        except KeyError as exc:
            _fail("SCHEMA_INVALID", f"missing parent contract field: {exc.args[0]}")
        raise AssertionError("_fail must raise")


ParentContractInput = ParentContract


def _proof_from_mapping(value: Any) -> BoundarySubsetProof:
    candidate = _mapping(value, "boundary_subset_proof")
    allowed = {"valid", "parent_scope_digest", "child_scope_digest", "checks"}
    unknown = sorted(set(candidate) - allowed)
    if unknown:
        _fail("SCHEMA_INVALID", f"unsupported boundary_subset_proof fields: {', '.join(unknown)}")
    try:
        proof = BoundarySubsetProof(
            parent_scope_digest=candidate["parent_scope_digest"],
            child_scope_digest=candidate["child_scope_digest"],
            checks=tuple(candidate["checks"]),
            valid=candidate["valid"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"boundary_subset_proof is invalid: {exc}")
    return proof


def _child_payload(
    *,
    child_id: str,
    parent_contract_id: str,
    parent_contract_digest: str,
    run_id: str,
    node_id: str,
    plan_version: str,
    lens: str,
    objective: str,
    acceptance_criteria: tuple[str, ...],
    boundary: ExecutionBoundary,
    parent_boundary_digest: str,
    proof: BoundarySubsetProof,
    standards_profile_ref: str,
    standards_profile: Mapping[str, str],
    source_manifest_ref: str,
    source_digest: str,
    source_manifest: Mapping[str, Any],
    agent_instance: str,
    child_depth: int,
    include_digest: bool = False,
    contract_digest: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "protocol": CHILD_CONTRACT_PROTOCOL,
        "child_id": child_id,
        "parent_contract_id": parent_contract_id,
        "parent_contract_digest": parent_contract_digest,
        "run_id": run_id,
        "node_id": node_id,
        "plan_version": plan_version,
        "lens": lens,
        "objective": objective,
        "acceptance_criteria": list(acceptance_criteria),
        "scope": _scope(boundary),
        "boundary_digest": boundary.digest(),
        "parent_boundary_digest": parent_boundary_digest,
        "boundary_subset_proof": proof.to_dict(),
        "standards_profile_ref": standards_profile_ref,
        "standards_profile": copy.deepcopy(dict(standards_profile)),
        "source_manifest_ref": source_manifest_ref,
        "source_digest": source_digest,
        "source_manifest": copy.deepcopy(dict(source_manifest)),
        "agent_instance": agent_instance,
        "child_depth": child_depth,
    }
    if include_digest:
        payload["digest"] = contract_digest
    return payload


@dataclass(frozen=True, slots=True)
class ChildContract:
    """Immutable, digest-bound child execution contract."""

    child_id: str
    parent_contract_id: str
    parent_contract_digest: str
    run_id: str
    node_id: str
    plan_version: str
    lens: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    boundary: ExecutionBoundary
    parent_boundary_digest: str
    boundary_subset_proof: BoundarySubsetProof
    standards_profile_ref: str
    standards_profile: Mapping[str, str]
    source_manifest_ref: str
    source_digest: str
    source_manifest: Mapping[str, Any]
    agent_instance: str
    child_depth: int
    contract_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_id", _text(self.child_id, "child_id", max_bytes=MAX_CHILD_ID_LENGTH, identifier=True))
        object.__setattr__(self, "parent_contract_id", _text(self.parent_contract_id, "parent_contract_id", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True))
        object.__setattr__(self, "parent_contract_digest", _digest(self.parent_contract_digest, "parent_contract_digest"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True))
        object.__setattr__(self, "node_id", _text(self.node_id, "node_id", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True))
        object.__setattr__(self, "plan_version", _text(self.plan_version, "plan_version", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True))
        object.__setattr__(self, "lens", _text(self.lens, "lens", max_bytes=MAX_LENS_LENGTH, identifier=True))
        object.__setattr__(self, "objective", _text(self.objective, "objective", max_bytes=MAX_OBJECTIVE_LENGTH))
        object.__setattr__(self, "acceptance_criteria", _bounded_criteria(self.acceptance_criteria, "acceptance_criteria"))
        if not isinstance(self.boundary, ExecutionBoundary):
            object.__setattr__(self, "boundary", _boundary(self.boundary, "child boundary"))  # type: ignore[arg-type]
        if not isinstance(self.boundary_subset_proof, BoundarySubsetProof):
            _fail("SCHEMA_INVALID", "boundary_subset_proof must be a BoundarySubsetProof")
        if self.boundary_subset_proof.child_scope_digest != self.boundary.digest():
            _fail("BOUNDARY_MISMATCH", "subset proof does not bind child boundary")
        if self.parent_boundary_digest != self.boundary_subset_proof.parent_scope_digest:
            _fail("BOUNDARY_MISMATCH", "parent_boundary_digest does not bind subset proof")
        object.__setattr__(self, "parent_boundary_digest", _digest(self.parent_boundary_digest, "parent_boundary_digest"))
        object.__setattr__(self, "standards_profile_ref", _text(self.standards_profile_ref, "standards_profile_ref", max_bytes=_MAX_IDENTIFIER_LENGTH))
        object.__setattr__(self, "standards_profile", _normalize_profile(self.standards_profile, "standards_profile"))
        object.__setattr__(self, "source_manifest_ref", _text(self.source_manifest_ref, "source_manifest_ref", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True))
        object.__setattr__(self, "source_digest", _digest(self.source_digest, "source_digest"))
        manifest = _normalize_manifest(self.source_manifest, "source_manifest")
        if manifest["digest"] != self.source_digest:
            _fail("CONTRACT_MISMATCH", "source_manifest.digest does not match source_digest")
        object.__setattr__(self, "source_manifest", manifest)
        object.__setattr__(self, "agent_instance", _text(self.agent_instance, "agent_instance", max_bytes=_MAX_IDENTIFIER_LENGTH, identifier=True))
        if isinstance(self.child_depth, bool) or not isinstance(self.child_depth, int) or self.child_depth < 0:
            _fail("SCHEMA_INVALID", "child_depth must be an integer >= 0")
        expected = canonical_digest(
            _child_payload(
                child_id=self.child_id,
                parent_contract_id=self.parent_contract_id,
                parent_contract_digest=self.parent_contract_digest,
                run_id=self.run_id,
                node_id=self.node_id,
                plan_version=self.plan_version,
                lens=self.lens,
                objective=self.objective,
                acceptance_criteria=self.acceptance_criteria,
                boundary=self.boundary,
                parent_boundary_digest=self.parent_boundary_digest,
                proof=self.boundary_subset_proof,
                standards_profile_ref=self.standards_profile_ref,
                standards_profile=self.standards_profile,
                source_manifest_ref=self.source_manifest_ref,
                source_digest=self.source_digest,
                source_manifest=self.source_manifest,
                agent_instance=self.agent_instance,
                child_depth=self.child_depth,
            )
        )
        if _digest(self.contract_digest, "digest") != expected:
            _fail("DIGEST_MISMATCH", f"child contract digest does not match canonical payload; expected {expected}")
        object.__setattr__(self, "contract_digest", expected)

    @property
    def boundary_digest(self) -> str:
        return self.boundary.digest()

    @property
    def digest_value(self) -> str:
        """Non-callable compatibility alias for consumers preferring a value."""

        return self.contract_digest

    def digest(self) -> str:
        return self.contract_digest

    def canonical_bytes(self) -> bytes:
        return mailbox_canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return _child_payload(
            child_id=self.child_id,
            parent_contract_id=self.parent_contract_id,
            parent_contract_digest=self.parent_contract_digest,
            run_id=self.run_id,
            node_id=self.node_id,
            plan_version=self.plan_version,
            lens=self.lens,
            objective=self.objective,
            acceptance_criteria=self.acceptance_criteria,
            boundary=self.boundary,
            parent_boundary_digest=self.parent_boundary_digest,
            proof=self.boundary_subset_proof,
            standards_profile_ref=self.standards_profile_ref,
            standards_profile=self.standards_profile,
            source_manifest_ref=self.source_manifest_ref,
            source_digest=self.source_digest,
            source_manifest=self.source_manifest,
            agent_instance=self.agent_instance,
            child_depth=self.child_depth,
            include_digest=True,
            contract_digest=self.contract_digest,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChildContract":
        if not isinstance(payload, Mapping):
            _fail("SCHEMA_INVALID", "child contract must be an object")
        candidate = copy.deepcopy(dict(payload))
        missing = sorted(_SERIALIZED_FIELDS - set(candidate))
        if missing:
            _fail("SCHEMA_INVALID", f"missing child contract fields: {', '.join(missing)}")
        unknown = sorted(set(candidate) - _SERIALIZED_FIELDS)
        if unknown:
            _fail("SCHEMA_INVALID", f"unsupported child contract fields: {', '.join(unknown)}")
        if candidate["protocol"] != CHILD_CONTRACT_PROTOCOL:
            _fail("SCHEMA_INVALID", f"expected {CHILD_CONTRACT_PROTOCOL}")
        scope = _mapping(candidate["scope"], "scope")
        if "scope_digest" in scope:
            _fail("SCHEMA_INVALID", "scope must not carry a second digest field")
        scope["scope_digest"] = candidate["boundary_digest"]
        proof = _proof_from_mapping(candidate["boundary_subset_proof"])
        try:
            boundary = ExecutionBoundary.from_dict(scope)
            return cls(
                child_id=candidate["child_id"],
                parent_contract_id=candidate["parent_contract_id"],
                parent_contract_digest=candidate["parent_contract_digest"],
                run_id=candidate["run_id"],
                node_id=candidate["node_id"],
                plan_version=candidate["plan_version"],
                lens=candidate["lens"],
                objective=candidate["objective"],
                acceptance_criteria=candidate["acceptance_criteria"],
                boundary=boundary,
                parent_boundary_digest=candidate["parent_boundary_digest"],
                boundary_subset_proof=proof,
                standards_profile_ref=candidate["standards_profile_ref"],
                standards_profile=candidate["standards_profile"],
                source_manifest_ref=candidate["source_manifest_ref"],
                source_digest=candidate["source_digest"],
                source_manifest=candidate["source_manifest"],
                agent_instance=candidate["agent_instance"],
                child_depth=candidate["child_depth"],
                contract_digest=candidate["digest"],
            )
        except ChildContractError:
            raise
        except ExecutionBoundaryValidationError as exc:
            raise ChildContractError(
                exc.code,
                str(exc),
                failed_checks=exc.failed_checks,
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            _fail("SCHEMA_INVALID", f"child contract is invalid: {exc}")
        raise AssertionError("_fail must raise")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ChildContract":
        return cls.from_dict(payload)


class ChildContractGenerator:
    """Pure generator that keeps every child bound to one parent snapshot."""

    def __init__(self, parent: ParentInput) -> None:
        self.parent = ParentContract.from_mapping(parent)

    def generate(
        self,
        proposal: ChildContractInput | Mapping[str, Any],
    ) -> ChildContract:
        spec = proposal if isinstance(proposal, ChildContractInput) else ChildContractInput.from_mapping(proposal)
        if spec.standards_profile is not None:
            proposed_profile = _normalize_profile(spec.standards_profile, "child standards_profile")
            if proposed_profile != dict(self.parent.standards_profile):
                _fail("CONTRACT_MISMATCH", "child standards_profile must inherit the exact parent identity")
        if spec.source_manifest is not None:
            proposed_manifest = _normalize_manifest(spec.source_manifest, "child source_manifest")
            if proposed_manifest != dict(self.parent.source_manifest):
                _fail("CONTRACT_MISMATCH", "child source_manifest must inherit the exact parent identity")

        objective = spec.objective or self.parent.objective
        if objective is None:
            _fail("SCHEMA_INVALID", "child objective must be explicit when parent objective is absent")
        criteria = (
            tuple(spec.acceptance_criteria)
            if spec.acceptance_criteria is not None
            else self.parent.acceptance_criteria
        )
        if not set(criteria).issubset(set(self.parent.acceptance_criteria)):
            _fail("CONTRACT_MISMATCH", "child acceptance criteria must be a subset of parent criteria")
        agent_instance = spec.agent_instance or self.parent.agent_instance
        if agent_instance is None:
            _fail("SCHEMA_INVALID", "child agent_instance must be explicit or inherited")

        # This is the only authority decision in the generator.  The existing
        # executable validator supplies the machine-readable failed dimensions
        # and REPLAN_REQUIRED outcome; no field is truncated or repaired.
        proof = self.parent.boundary.validate_child_subset(
            spec.boundary,
            child_depth=spec.child_depth,
        )
        values = {
            "child_id": spec.child_id,
            "parent_contract_id": self.parent.contract_id,
            "parent_contract_digest": self.parent.contract_digest,
            "run_id": self.parent.run_id,
            "node_id": self.parent.node_id,
            "plan_version": self.parent.plan_version,
            "lens": spec.lens,
            "objective": objective,
            "acceptance_criteria": criteria,
            "boundary": spec.boundary,
            "parent_boundary_digest": self.parent.boundary.digest(),
            "proof": proof,
            "standards_profile_ref": self.parent.standards_profile_ref,
            "standards_profile": self.parent.standards_profile,
            "source_manifest_ref": self.parent.source_manifest_ref,
            "source_digest": self.parent.source_digest,
            "source_manifest": self.parent.source_manifest,
            "agent_instance": agent_instance,
            "child_depth": spec.child_depth,
        }
        digest_value = canonical_digest(_child_payload(**values))
        contract_values = dict(values)
        contract_values.pop("proof")
        contract_values["boundary_subset_proof"] = proof
        return ChildContract(contract_digest=digest_value, **contract_values)

    def generate_many(
        self,
        proposals: Sequence[ChildContractInput | Mapping[str, Any]],
    ) -> tuple[ChildContract, ...]:
        if isinstance(proposals, (str, bytes, Mapping)):
            _fail("SCHEMA_INVALID", "child proposals must be an array")
        try:
            items = tuple(proposals)
        except (TypeError, ValueError) as exc:
            _fail("SCHEMA_INVALID", f"child proposals must be an array: {exc}")
        if len(items) > self.parent.boundary.max_children:
            _fail(
                REPLAN_REQUIRED,
                "child proposal count exceeds parent max_children; refusing silent truncation",
                failed_checks=("child_count_within_parent",),
            )
        seen: set[str] = set()
        result: list[ChildContract] = []
        for item in items:
            spec = item if isinstance(item, ChildContractInput) else ChildContractInput.from_mapping(item)
            if spec.child_id in seen:
                _fail("SCHEMA_INVALID", f"duplicate child_id: {spec.child_id}")
            seen.add(spec.child_id)
            result.append(self.generate(spec))
        return tuple(result)


def generate_child_contract(
    parent: ParentInput,
    proposal: ChildContractInput | Mapping[str, Any] | None = None,
    *,
    child_id: str | None = None,
    lens: str | None = None,
    child_boundary: BoundaryInput | None = None,
    boundary: BoundaryInput | None = None,
    objective: str | None = None,
    acceptance_criteria: Sequence[str] | None = None,
    agent_instance: str | None = None,
    child_depth: int = 0,
    standards_profile: Mapping[str, Any] | StandardsProfile | None = None,
    source_manifest: Mapping[str, Any] | None = None,
) -> ChildContract:
    """Generate one child contract from an explicit parent and proposal."""
    supplied_kwargs = {
        "child_id": child_id,
        "lens": lens,
        "child_boundary": child_boundary,
        "boundary": boundary,
        "objective": objective,
        "acceptance_criteria": acceptance_criteria,
        "agent_instance": agent_instance,
        "standards_profile": standards_profile,
        "source_manifest": source_manifest,
    }
    if child_boundary is not None and boundary is not None:
        _fail("CONTRACT_MISMATCH", "pass child_boundary or boundary, not both")
    if child_boundary is not None:
        supplied_kwargs["boundary"] = child_boundary
        supplied_kwargs["child_boundary"] = None
    if proposal is not None and any(value is not None for value in supplied_kwargs.values()):
        _fail("SCHEMA_INVALID", "pass a child proposal or keyword proposal fields, not both")
    if proposal is None:
        proposal_map: dict[str, Any] = {
            key: value
            for key, value in supplied_kwargs.items()
            if value is not None
        }
        if "boundary" not in proposal_map:
            _fail("SCHEMA_INVALID", "child boundary is required")
        if child_depth != 0:
            proposal_map["child_depth"] = child_depth
        proposal = proposal_map
    spec = proposal if isinstance(proposal, ChildContractInput) else ChildContractInput.from_mapping(proposal)
    return ChildContractGenerator(parent).generate(spec)


def generate_child_contracts(
    parent: ParentInput,
    proposals: Sequence[ChildContractInput | Mapping[str, Any]],
) -> tuple[ChildContract, ...]:
    """Generate a bounded ordered set without silently dropping proposals."""
    return ChildContractGenerator(parent).generate_many(proposals)


# Descriptive aliases keep the pure seam discoverable for adapters using
# create/build terminology without creating alternate implementations.
ChildContractFactory = ChildContractGenerator
create_child_contract = generate_child_contract
build_child_contract = generate_child_contract
generate_children = generate_child_contracts


__all__ = [
    "CHILD_CONTRACT_PROTOCOL",
    "MAX_ACCEPTANCE_CRITERIA",
    "MAX_ACCEPTANCE_CRITERION_LENGTH",
    "MAX_CHILD_ID_LENGTH",
    "MAX_LENS_LENGTH",
    "MAX_OBJECTIVE_LENGTH",
    "MAX_SOURCE_REFS",
    "BoundaryInput",
    "ChildContract",
    "ChildContractError",
    "ChildContractFactory",
    "ChildContractGenerator",
    "ChildContractInput",
    "ChildContractSpec",
    "ParentContract",
    "ParentContractInput",
    "build_child_contract",
    "create_child_contract",
    "generate_child_contract",
    "generate_child_contracts",
    "generate_children",
]
