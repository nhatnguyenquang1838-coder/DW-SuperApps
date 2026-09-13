"""TC-MBX-506 provider-neutral durable Fanout Manifest seam.

The manifest is an immutable, canonical, reference-only snapshot. Each semantic
child transition returns a new manifest version and digest; a persistence adapter
may store those bytes later without changing this contract. This module does
not invoke providers, write GitHub/Slack/mailbox state, or enable runtime
fan-out.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from taskcontroller.execution.fanout import (
    ChildAttemptBinding,
    ChildCompletion,
    ChildLifecycle,
    ChildLifecycleError,
    CompletionStatus,
    FanoutCoordinator,
    FanoutPlan,
    JoinSemantics,
    JoinStatus,
    transition_child_lifecycle,
)
from taskcontroller.controlplane.generation_fence import (
    GenerationFenceDecision,
    GenerationFenceError,
    evaluate_generation_fence,
)
from taskcontroller.interaction.mailbox_v2 import canonical_bytes, canonical_digest


FANOUT_MANIFEST_PROTOCOL = "dw.taskcontroller.fanout-manifest/v1"
MANIFEST_VERSION = 1
DEFAULT_CHILD_TIMEOUT_SECONDS = 1800
MAX_MANIFEST_CHILDREN = 64
MAX_MANIFEST_VERSION = 2**31 - 1
MAX_IDENTIFIER_BYTES = 256
MAX_RESULT_REF_BYTES = 2048

import re as _re

_DIGEST_RE = _re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class FanoutManifestError(ValueError):
    """Stable fail-closed error for manifest validation and join decisions."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise FanoutManifestError(code, message)


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


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name, max_bytes=MAX_RESULT_REF_BYTES)


def _optional_digest(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _digest(value, name)


def _optional_identifier(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name, max_bytes=MAX_IDENTIFIER_BYTES, identifier=True)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail("SCHEMA_INVALID", f"{name} must be a positive integer")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("SCHEMA_INVALID", f"{name} must be a non-negative integer")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("SCHEMA_INVALID", f"{name} must be an object")
    if any(not isinstance(key, str) for key in value):
        _fail("SCHEMA_INVALID", f"{name} keys must be strings")
    return dict(value)


def _lifecycle(value: ChildLifecycle | str, name: str) -> ChildLifecycle:
    try:
        return value if isinstance(value, ChildLifecycle) else ChildLifecycle(value)
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"{name} is not a valid ChildLifecycle: {exc}")
    raise AssertionError("_fail must raise")


@dataclass(frozen=True, slots=True)
class ManifestParentIdentity:
    """Controller-owned parent identity and immutable source digests."""

    run_id: str
    node_id: str
    plan_version: str
    contract_id: str
    contract_digest: str
    boundary_digest: str
    source_manifest_ref: str
    source_digest: str
    standards_profile_ref: str
    standards_profile_digest: str
    attempt_id: str
    lease_generation: int | None = None
    fencing_token: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "node_id",
            "plan_version",
            "contract_id",
            "source_manifest_ref",
            "standards_profile_ref",
            "attempt_id",
        ):
            object.__setattr__(
                self,
                name,
                _text(
                    getattr(self, name),
                    name,
                    max_bytes=MAX_IDENTIFIER_BYTES,
                    identifier=name not in {"source_manifest_ref", "standards_profile_ref"},
                ),
            )
        for name in (
            "contract_digest",
            "boundary_digest",
            "source_digest",
            "standards_profile_digest",
        ):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        if self.lease_generation is not None:
            object.__setattr__(
                self,
                "lease_generation",
                _non_negative_int(self.lease_generation, "lease_generation"),
            )
        if self.fencing_token is not None:
            object.__setattr__(self, "fencing_token", _optional_text(self.fencing_token, "fencing_token"))

    @classmethod
    def from_plan(
        cls,
        plan: FanoutPlan,
        *,
        attempt_id: str,
        lease_generation: int | None = None,
        fencing_token: str | None = None,
    ) -> "ManifestParentIdentity":
        if not isinstance(plan, FanoutPlan):
            _fail("SCHEMA_INVALID", "plan must be a FanoutPlan")
        if not plan.children:
            _fail("SCHEMA_INVALID", "plan must contain at least one child")
        first = plan.children[0]
        expected = {
            "parent_contract_id": plan.parent_contract_id,
            "parent_contract_digest": plan.parent_contract_digest,
            "run_id": plan.run_id,
            "node_id": plan.node_id,
            "plan_version": plan.plan_version,
            "parent_boundary_digest": plan.parent_boundary_digest,
            "source_manifest_ref": first.source_manifest_ref,
            "source_digest": first.source_digest,
            "standards_profile_ref": first.standards_profile_ref,
            "standards_profile_digest": first.standards_profile["digest"],
        }
        for child in plan.children:
            actual = {
                "parent_contract_id": child.parent_contract_id,
                "parent_contract_digest": child.parent_contract_digest,
                "run_id": child.run_id,
                "node_id": child.node_id,
                "plan_version": child.plan_version,
                "parent_boundary_digest": child.parent_boundary_digest,
                "source_manifest_ref": child.source_manifest_ref,
                "source_digest": child.source_digest,
                "standards_profile_ref": child.standards_profile_ref,
                "standards_profile_digest": child.standards_profile["digest"],
            }
            if actual != expected:
                _fail(
                    "CONTRACT_MISMATCH",
                    f"child identity/digest does not match parent for {child.child_id}",
                )
        return cls(
            run_id=plan.run_id,
            node_id=plan.node_id,
            plan_version=plan.plan_version,
            contract_id=plan.parent_contract_id,
            contract_digest=plan.parent_contract_digest,
            boundary_digest=plan.parent_boundary_digest,
            source_manifest_ref=first.source_manifest_ref,
            source_digest=first.source_digest,
            standards_profile_ref=first.standards_profile_ref,
            standards_profile_digest=first.standards_profile["digest"],
            attempt_id=attempt_id,
            lease_generation=lease_generation,
            fencing_token=fencing_token,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ManifestParentIdentity":
        candidate = _mapping(value, "parent")
        required = {
            "run_id",
            "node_id",
            "plan_version",
            "contract_id",
            "contract_digest",
            "boundary_digest",
            "source_manifest_ref",
            "source_digest",
            "standards_profile_ref",
            "standards_profile_digest",
            "attempt_id",
            "lease_generation",
        }
        optional = {"fencing_token"}
        unknown = sorted(set(candidate) - required - optional)
        missing = sorted(required - set(candidate))
        if unknown:
            _fail("SCHEMA_INVALID", f"unsupported parent fields: {', '.join(unknown)}")
        if missing:
            _fail("SCHEMA_INVALID", f"missing parent fields: {', '.join(missing)}")
        try:
            return cls(**candidate)
        except TypeError as exc:
            _fail("SCHEMA_INVALID", f"parent identity is incomplete: {exc}")
        raise AssertionError("_fail must raise")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "plan_version": self.plan_version,
            "contract_id": self.contract_id,
            "contract_digest": self.contract_digest,
            "boundary_digest": self.boundary_digest,
            "source_manifest_ref": self.source_manifest_ref,
            "source_digest": self.source_digest,
            "standards_profile_ref": self.standards_profile_ref,
            "standards_profile_digest": self.standards_profile_digest,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
        }
        if self.fencing_token is not None:
            payload["fencing_token"] = self.fencing_token
        return payload

    def generation_identity(self) -> dict[str, Any]:
        """Return the v2 parent fence, rejecting legacy-unbound manifests."""
        if self.lease_generation is None or self.fencing_token is None:
            _fail(
                "SCHEMA_INVALID",
                "current-generation manifest requires lease_generation and fencing_token",
            )
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
            "fencing_token": self.fencing_token,
        }

    def generation_decision(self, current: Mapping[str, Any]) -> GenerationFenceDecision:
        try:
            return evaluate_generation_fence(self.generation_identity(), current)
        except GenerationFenceError as exc:
            raise FanoutManifestError(exc.code, str(exc)) from exc


@dataclass(frozen=True, slots=True)
class FanoutManifestChild:
    """Reference-only child attempt record stored in a manifest snapshot."""

    child_id: str
    lens: str
    agent_instance: str
    attempt_id: str
    status: ChildLifecycle
    timeout_seconds: int
    child_contract_digest: str
    source_digest: str
    standards_profile_digest: str
    result_ref: str | None = None
    result_digest: str | None = None
    plan_version: str | None = None
    plan_digest: str | None = None
    parent_attempt_id: str | None = None
    lease_generation: int | None = None

    def __post_init__(self) -> None:
        for name in ("child_id", "lens", "agent_instance", "attempt_id"):
            object.__setattr__(
                self,
                name,
                _text(getattr(self, name), name, max_bytes=MAX_IDENTIFIER_BYTES, identifier=True),
            )
        object.__setattr__(self, "status", _lifecycle(self.status, "status"))
        object.__setattr__(
            self,
            "timeout_seconds",
            _positive_int(self.timeout_seconds, "timeout_seconds"),
        )
        for name in ("child_contract_digest", "source_digest", "standards_profile_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        result_ref = _optional_text(self.result_ref, "result_ref")
        result_digest = _optional_digest(self.result_digest, "result_digest")
        if (result_ref is None) != (result_digest is None):
            _fail("SCHEMA_INVALID", "result_ref and result_digest must be supplied together")
        if self.status.is_terminal and result_ref is None:
            _fail("SCHEMA_INVALID", "terminal child requires result_ref and result_digest")
        if not self.status.is_terminal and result_ref is not None:
            _fail("SCHEMA_INVALID", "non-terminal child cannot carry result evidence")
        object.__setattr__(self, "result_ref", result_ref)
        object.__setattr__(self, "result_digest", result_digest)

        plan_version = _optional_identifier(self.plan_version, "plan_version")
        plan_digest = _optional_digest(self.plan_digest, "plan_digest")
        parent_attempt_id = _optional_identifier(
            self.parent_attempt_id,
            "parent_attempt_id",
        )
        binding_present = any(
            value is not None for value in (plan_version, plan_digest, parent_attempt_id, self.lease_generation)
        )
        if binding_present and any(
            value is None for value in (plan_version, plan_digest, parent_attempt_id)
        ):
            _fail(
                "SCHEMA_INVALID",
                "bound manifest child requires plan_version, plan_digest and parent_attempt_id",
            )
        if self.lease_generation is not None:
            object.__setattr__(
                self,
                "lease_generation",
                _non_negative_int(self.lease_generation, "lease_generation"),
            )
        object.__setattr__(self, "plan_version", plan_version)
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(self, "parent_attempt_id", parent_attempt_id)

    @property
    def has_parent_binding(self) -> bool:
        return self.plan_version is not None

    @property
    def attempt_binding(self) -> ChildAttemptBinding | None:
        if not self.has_parent_binding:
            return None
        return ChildAttemptBinding(
            plan_version=self.plan_version,
            plan_digest=self.plan_digest,
            parent_attempt_id=self.parent_attempt_id,
            lease_generation=self.lease_generation,
            source_digest=self.source_digest,
            standards_profile_digest=self.standards_profile_digest,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FanoutManifestChild":
        candidate = _mapping(value, "children[]")
        required = {
            "child_id",
            "lens",
            "agent_instance",
            "attempt_id",
            "status",
            "timeout_seconds",
            "child_contract_digest",
            "source_digest",
            "standards_profile_digest",
            "result_ref",
            "result_digest",
        }
        optional = {
            "plan_version",
            "plan_digest",
            "parent_attempt_id",
            "lease_generation",
        }
        unknown = sorted(set(candidate) - required - optional)
        missing = sorted(required - set(candidate))
        if unknown:
            _fail("SCHEMA_INVALID", f"unsupported child fields: {', '.join(unknown)}")
        if missing:
            _fail("SCHEMA_INVALID", f"missing child fields: {', '.join(missing)}")
        try:
            return cls(**candidate)
        except TypeError as exc:
            _fail("SCHEMA_INVALID", f"child manifest record is incomplete: {exc}")
        raise AssertionError("_fail must raise")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "child_id": self.child_id,
            "lens": self.lens,
            "agent_instance": self.agent_instance,
            "attempt_id": self.attempt_id,
            "status": self.status.value,
            "timeout_seconds": self.timeout_seconds,
            "child_contract_digest": self.child_contract_digest,
            "source_digest": self.source_digest,
            "standards_profile_digest": self.standards_profile_digest,
            "result_ref": self.result_ref,
            "result_digest": self.result_digest,
        }
        if self.has_parent_binding:
            payload.update(
                {
                    "plan_version": self.plan_version,
                    "plan_digest": self.plan_digest,
                    "parent_attempt_id": self.parent_attempt_id,
                    "lease_generation": self.lease_generation,
                }
            )
        return payload


@dataclass(frozen=True, slots=True)
class ManifestJoinDecision:
    """Current manifest join projection; no raw child conversation is needed."""

    status: JoinStatus
    manifest_id: str
    manifest_version: int
    manifest_digest: str
    missing_child_ids: tuple[str, ...]
    failed_child_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "manifest_digest": self.manifest_digest,
            "missing_child_ids": list(self.missing_child_ids),
            "failed_child_ids": list(self.failed_child_ids),
        }


@dataclass(frozen=True, slots=True)
class FanoutManifest:
    """Canonical immutable manifest snapshot for one parent execution attempt."""

    manifest_id: str
    manifest_version: int
    parent: ManifestParentIdentity
    join_semantics: JoinSemantics
    children: tuple[FanoutManifestChild, ...]
    manifest_digest: str
    stale_children: tuple[FanoutManifestChild, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "manifest_id",
            _text(self.manifest_id, "manifest_id", max_bytes=MAX_IDENTIFIER_BYTES, identifier=True),
        )
        if isinstance(self.manifest_version, bool) or not isinstance(self.manifest_version, int):
            _fail("SCHEMA_INVALID", "manifest_version must be an integer")
        if not 1 <= self.manifest_version <= MAX_MANIFEST_VERSION:
            _fail("SCHEMA_INVALID", "manifest_version is outside the supported range")
        if not isinstance(self.parent, ManifestParentIdentity):
            _fail("SCHEMA_INVALID", "parent must be a ManifestParentIdentity")
        if not isinstance(self.join_semantics, JoinSemantics):
            _fail("SCHEMA_INVALID", "join_semantics must be JoinSemantics")
        if not isinstance(self.children, (tuple, list)) or not self.children:
            _fail("SCHEMA_INVALID", "children must contain at least one manifest record")
        if len(self.children) > MAX_MANIFEST_CHILDREN:
            _fail("REPLAN_REQUIRED", "manifest exceeds bounded child count")
        if any(not isinstance(item, FanoutManifestChild) for item in self.children):
            _fail("SCHEMA_INVALID", "children must contain FanoutManifestChild values")
        normalized = tuple(sorted(self.children, key=lambda item: item.child_id))
        child_ids = tuple(item.child_id for item in normalized)
        if len(set(child_ids)) != len(child_ids):
            _fail("SCHEMA_INVALID", "manifest child_id values must be unique")
        object.__setattr__(self, "children", normalized)
        for child in normalized:
            if not child.has_parent_binding:
                continue
            if child.plan_version != self.parent.plan_version:
                _fail("CONTRACT_MISMATCH", f"child plan_version mismatch: {child.child_id}")
            if child.parent_attempt_id != self.parent.attempt_id:
                _fail("CONTRACT_MISMATCH", f"child parent attempt mismatch: {child.child_id}")
            if child.lease_generation != self.parent.lease_generation:
                _fail("CONTRACT_MISMATCH", f"child lease generation mismatch: {child.child_id}")
        plan_digests = {child.plan_digest for child in normalized if child.plan_digest is not None}
        if len(plan_digests) > 1:
            _fail("CONTRACT_MISMATCH", "manifest children have conflicting plan digests")

        raw_stale = self.stale_children
        if not isinstance(raw_stale, (tuple, list)):
            _fail("SCHEMA_INVALID", "stale_children must be an array")
        stale = tuple(raw_stale)
        if any(not isinstance(item, FanoutManifestChild) for item in stale):
            _fail("SCHEMA_INVALID", "stale_children must contain FanoutManifestChild values")
        if any(item.status is not ChildLifecycle.STALE for item in stale):
            _fail("SCHEMA_INVALID", "stale_children must contain STALE records")
        object.__setattr__(
            self,
            "stale_children",
            tuple(sorted(stale, key=lambda item: (item.child_id, item.attempt_id))),
        )
        expected = canonical_digest(self._payload())
        supplied = _digest(self.manifest_digest, "manifest_digest")
        if supplied != expected:
            _fail("DIGEST_MISMATCH", "manifest_digest does not match canonical manifest bytes")
        object.__setattr__(self, "manifest_digest", expected)

    def _payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol": FANOUT_MANIFEST_PROTOCOL,
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "parent": self.parent.to_dict(),
            "join_semantics": self.join_semantics.to_dict(),
            "children": [item.to_dict() for item in self.children],
        }
        if self.stale_children:
            payload["stale_children"] = [item.to_dict() for item in self.stale_children]
        return payload

    @classmethod
    def from_plan(
        cls,
        plan: FanoutPlan,
        *,
        attempt_id: str,
        lease_generation: int | None = None,
        fencing_token: str | None = None,
        timeout_seconds: int = DEFAULT_CHILD_TIMEOUT_SECONDS,
        manifest_id: str | None = None,
        child_attempt_ids: Mapping[str, str] | None = None,
        _allow_partial_child_attempt_ids: bool = False,
    ) -> "FanoutManifest":
        parent = ManifestParentIdentity.from_plan(
            plan,
            attempt_id=attempt_id,
            lease_generation=lease_generation,
            fencing_token=fencing_token,
        )
        timeout = _positive_int(timeout_seconds, "timeout_seconds")
        attempts = _mapping(child_attempt_ids, "child_attempt_ids") if child_attempt_ids is not None else {}
        expected_ids = {child.child_id for child in plan.children}
        unknown = sorted(set(attempts) - expected_ids)
        missing = sorted(expected_ids - set(attempts))
        if unknown:
            _fail("SCHEMA_INVALID", f"unknown child attempt IDs: {', '.join(unknown)}")
        records = tuple(
            FanoutManifestChild(
                child_id=child.child_id,
                lens=child.lens,
                agent_instance=child.agent_instance,
                attempt_id=(
                    attempts[child.child_id]
                    if child.child_id in attempts
                    else f"{attempt_id}:{child.child_id}"
                ),
                status=ChildLifecycle.PLANNED,
                timeout_seconds=timeout,
                child_contract_digest=child.contract_digest,
                source_digest=child.source_digest,
                standards_profile_digest=child.standards_profile["digest"],
                plan_version=plan.plan_version,
                plan_digest=plan.plan_digest,
                parent_attempt_id=parent.attempt_id,
                lease_generation=parent.lease_generation,
            )
            for child in plan.children
        )
        if missing and child_attempt_ids is not None and not _allow_partial_child_attempt_ids:
            _fail("SCHEMA_INVALID", f"missing child attempt IDs: {', '.join(missing)}")
        selected_id = _text(
            manifest_id or f"manifest:{plan.run_id}:{plan.node_id}:{plan.plan_version}",
            "manifest_id",
            max_bytes=MAX_IDENTIFIER_BYTES,
            identifier=True,
        )
        payload = {
            "protocol": FANOUT_MANIFEST_PROTOCOL,
            "manifest_id": selected_id,
            "manifest_version": 1,
            "parent": parent.to_dict(),
            "join_semantics": plan.join_semantics.to_dict(),
            "children": [item.to_dict() for item in records],
        }
        return cls(
            manifest_id=selected_id,
            manifest_version=1,
            parent=parent,
            join_semantics=plan.join_semantics,
            children=records,
            manifest_digest=canonical_digest(payload),
        )

    @classmethod
    def from_coordinator(
        cls,
        coordinator: FanoutCoordinator,
        *,
        attempt_id: str | None = None,
        lease_generation: int | None = None,
        fencing_token: str | None = None,
        timeout_seconds: int = DEFAULT_CHILD_TIMEOUT_SECONDS,
        manifest_id: str | None = None,
        child_attempt_ids: Mapping[str, str] | None = None,
    ) -> "FanoutManifest":
        if not isinstance(coordinator, FanoutCoordinator):
            _fail("SCHEMA_INVALID", "coordinator must be a FanoutCoordinator")
        selected_attempt_id = attempt_id or coordinator.parent_attempt_id
        if selected_attempt_id is None:
            _fail("CONTRACT_MISMATCH", "parent attempt_id is required for a manifest")
        if (
            coordinator.parent_attempt_id is not None
            and selected_attempt_id != coordinator.parent_attempt_id
        ):
            _fail("CONTRACT_MISMATCH", "manifest attempt_id does not match coordinator generation")
        selected_lease_generation = (
            lease_generation
            if lease_generation is not None
            else coordinator.lease_generation
        )
        if (
            coordinator.lease_generation is not None
            and selected_lease_generation != coordinator.lease_generation
        ):
            _fail("CONTRACT_MISMATCH", "manifest lease generation does not match coordinator")
        coordinator_attempt_ids = (
            dict(coordinator.child_attempt_ids)
            if child_attempt_ids is None
            else child_attempt_ids
        )
        manifest = cls.from_plan(
            coordinator.plan,
            attempt_id=selected_attempt_id,
            lease_generation=selected_lease_generation,
            fencing_token=fencing_token,
            timeout_seconds=timeout_seconds,
            manifest_id=manifest_id,
            child_attempt_ids=coordinator_attempt_ids or None,
            _allow_partial_child_attempt_ids=True,
        )
        completions = {item.child_id: item for item in coordinator.completions}
        for child in coordinator.plan.children:
            state = coordinator.lifecycle_state(child.child_id)
            if state is ChildLifecycle.PLANNED:
                continue
            manifest = manifest.record_transition(child.child_id, ChildLifecycle.DISPATCHED)
            if state is ChildLifecycle.DISPATCHED:
                continue
            manifest = manifest.record_transition(child.child_id, ChildLifecycle.RUNNING)
            completion = completions.get(child.child_id)
            if completion is None:
                _fail("CONTRACT_MISMATCH", f"terminal child lacks completion: {child.child_id}")
            assert completion is not None
            manifest = manifest.record_transition(
                child.child_id,
                completion.lifecycle,
                result_ref=completion.result_ref,
                result_digest=completion.result_digest,
            )
        for completion in coordinator.stale_completions:
            manifest = manifest.record_completion(completion)
        return manifest

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FanoutManifest":
        candidate = _mapping(value, "manifest")
        required = {
            "protocol",
            "manifest_id",
            "manifest_version",
            "parent",
            "join_semantics",
            "children",
            "manifest_digest",
        }
        optional = {"stale_children"}
        unknown = sorted(set(candidate) - required - optional)
        missing = sorted(required - set(candidate))
        if unknown:
            _fail("SCHEMA_INVALID", f"unsupported manifest fields: {', '.join(unknown)}")
        if missing:
            _fail("SCHEMA_INVALID", f"missing manifest fields: {', '.join(missing)}")
        if candidate["protocol"] != FANOUT_MANIFEST_PROTOCOL:
            _fail("SCHEMA_INVALID", f"expected {FANOUT_MANIFEST_PROTOCOL}")
        raw_children = candidate["children"]
        if isinstance(raw_children, (str, bytes, Mapping)):
            _fail("SCHEMA_INVALID", "children must be an array")
        try:
            children = tuple(FanoutManifestChild.from_dict(item) for item in raw_children)
        except TypeError as exc:
            _fail("SCHEMA_INVALID", f"children must be an array: {exc}")
        raw_stale_children = candidate.get("stale_children", ())
        if isinstance(raw_stale_children, (str, bytes, Mapping)):
            _fail("SCHEMA_INVALID", "stale_children must be an array")
        try:
            stale_children = tuple(
                FanoutManifestChild.from_dict(item) for item in raw_stale_children
            )
        except TypeError as exc:
            _fail("SCHEMA_INVALID", f"stale_children must be an array: {exc}")
        semantics = _mapping(candidate["join_semantics"], "join_semantics")
        try:
            join_semantics = JoinSemantics(
                policy=semantics["policy"],
                acceptable_terminal_states=tuple(semantics["acceptable_terminal_states"]),
                partial_result_policy=semantics["partial_result_policy"],
                failure_policy=semantics["failure_policy"],
                timeout_policy=semantics["timeout_policy"],
                cancellation_policy=semantics["cancellation_policy"],
                stale_policy=semantics["stale_policy"],
            )
        except (KeyError, TypeError) as exc:
            _fail("SCHEMA_INVALID", f"join_semantics is incomplete: {exc}")
        try:
            return cls(
                manifest_id=candidate["manifest_id"],
                manifest_version=candidate["manifest_version"],
                parent=ManifestParentIdentity.from_dict(candidate["parent"]),
                join_semantics=join_semantics,
                children=children,
                manifest_digest=candidate["manifest_digest"],
                stale_children=stale_children,
            )
        except FanoutManifestError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            _fail("SCHEMA_INVALID", f"manifest is invalid: {exc}")
        raise AssertionError("_fail must raise")

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload(),
            "manifest_digest": self.manifest_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    def child(self, child_id: str) -> FanoutManifestChild:
        normalized = _text(child_id, "child_id", max_bytes=MAX_IDENTIFIER_BYTES, identifier=True)
        for child in self.children:
            if child.child_id == normalized:
                return child
        _fail("CONTRACT_MISMATCH", f"unknown manifest child: {normalized}")
        raise AssertionError("_fail must raise")

    def _snapshot(
        self,
        *,
        children: tuple[FanoutManifestChild, ...],
        parent: ManifestParentIdentity | None = None,
        stale_children: tuple[FanoutManifestChild, ...] | None = None,
    ) -> "FanoutManifest":
        selected_parent = self.parent if parent is None else parent
        selected_stale = self.stale_children if stale_children is None else stale_children
        next_version = self.manifest_version + 1
        payload: dict[str, Any] = {
            "protocol": FANOUT_MANIFEST_PROTOCOL,
            "manifest_id": self.manifest_id,
            "manifest_version": next_version,
            "parent": selected_parent.to_dict(),
            "join_semantics": self.join_semantics.to_dict(),
            "children": [item.to_dict() for item in children],
        }
        if selected_stale:
            payload["stale_children"] = [item.to_dict() for item in selected_stale]
        return FanoutManifest(
            manifest_id=self.manifest_id,
            manifest_version=next_version,
            parent=selected_parent,
            join_semantics=self.join_semantics,
            children=children,
            manifest_digest=canonical_digest(payload),
            stale_children=selected_stale,
        )

    def _replace_child(self, updated: FanoutManifestChild) -> "FanoutManifest":
        children = tuple(
            updated if item.child_id == updated.child_id else item for item in self.children
        )
        return self._snapshot(children=children)

    def record_transition(
        self,
        child_id: str,
        target: ChildLifecycle | str,
        *,
        result_ref: str | None = None,
        result_digest: str | None = None,
    ) -> "FanoutManifest":
        current = self.child(child_id)
        selected_target = _lifecycle(target, "target_lifecycle")
        try:
            next_state = transition_child_lifecycle(current.status, selected_target)
        except ChildLifecycleError as exc:
            raise FanoutManifestError(exc.code, str(exc)) from exc
        if next_state is current.status:
            supplied_ref = (
                _optional_text(result_ref, "result_ref")
                if result_ref is not None
                else current.result_ref
            )
            supplied_digest = (
                _optional_digest(result_digest, "result_digest")
                if result_digest is not None
                else current.result_digest
            )
            if supplied_ref != current.result_ref or supplied_digest != current.result_digest:
                _fail("IDEMPOTENCY_CONFLICT", f"replayed transition has different evidence: {child_id}")
            return self
        if next_state.is_terminal:
            if result_ref is None or result_digest is None:
                _fail("SCHEMA_INVALID", "terminal transition requires result_ref and result_digest")
            normalized_ref = _optional_text(result_ref, "result_ref")
            normalized_digest = _optional_digest(result_digest, "result_digest")
        else:
            if result_ref is not None or result_digest is not None:
                _fail("SCHEMA_INVALID", "non-terminal transition cannot carry result evidence")
            normalized_ref = None
            normalized_digest = None
        updated = replace(
            current,
            status=next_state,
            result_ref=normalized_ref,
            result_digest=normalized_digest,
        )
        return self._replace_child(updated)

    @property
    def plan_digest(self) -> str | None:
        digests = {child.plan_digest for child in self.children if child.plan_digest is not None}
        return next(iter(digests)) if len(digests) == 1 else None

    def _append_stale_child(self, stale: FanoutManifestChild) -> "FanoutManifest":
        key = (stale.child_id, stale.attempt_id)
        for prior in self.stale_children:
            prior_key = (prior.child_id, prior.attempt_id)
            if prior_key != key:
                continue
            if prior == stale:
                return self
            _fail("IDEMPOTENCY_CONFLICT", f"conflicting stale evidence: {stale.child_id}")
        return self._snapshot(
            children=self.children,
            stale_children=self.stale_children + (stale,),
        )

    def _stale_child_from_completion(
        self,
        completion: ChildCompletion,
    ) -> FanoutManifestChild:
        current = self.child(completion.child_id)
        attempt_id = completion.attempt_id or (
            f"stale:{completion.child_id}:{completion.result_digest[7:15]}"
        )
        return FanoutManifestChild(
            child_id=current.child_id,
            lens=current.lens,
            agent_instance=current.agent_instance,
            attempt_id=attempt_id,
            status=ChildLifecycle.STALE,
            timeout_seconds=current.timeout_seconds,
            child_contract_digest=current.child_contract_digest,
            source_digest=completion.source_digest or current.source_digest,
            standards_profile_digest=(
                completion.standards_profile_digest or current.standards_profile_digest
            ),
            result_ref=completion.result_ref,
            result_digest=completion.result_digest,
            plan_version=completion.plan_version or current.plan_version,
            plan_digest=completion.plan_digest or current.plan_digest,
            parent_attempt_id=completion.parent_attempt_id or current.parent_attempt_id,
            lease_generation=(
                completion.lease_generation
                if completion.has_parent_binding
                else current.lease_generation
            ),
        )

    def record_completion(self, completion: ChildCompletion) -> "FanoutManifest":
        """Record current evidence or retain a late completion as STALE."""
        if not isinstance(completion, ChildCompletion):
            _fail("SCHEMA_INVALID", "completion must be a ChildCompletion")
        current = self.child(completion.child_id)
        if completion.child_contract_digest != current.child_contract_digest:
            _fail("CONTRACT_MISMATCH", f"child contract digest mismatch: {completion.child_id}")
        if completion.evidence_only:
            return self._append_stale_child(self._stale_child_from_completion(completion))

        if current.has_parent_binding:
            if not completion.has_parent_binding:
                _fail(
                    "CONTRACT_MISMATCH",
                    f"current-generation completion is missing binding: {completion.child_id}",
                )
            mismatched = (
                completion.plan_version != current.plan_version
                or completion.plan_digest != current.plan_digest
                or completion.parent_attempt_id != current.parent_attempt_id
                or completion.lease_generation != current.lease_generation
                or completion.attempt_id != current.attempt_id
                or completion.source_digest not in (None, current.source_digest)
                or completion.standards_profile_digest
                not in (None, current.standards_profile_digest)
            )
            if mismatched:
                return self._append_stale_child(self._stale_child_from_completion(completion))
        elif completion.has_parent_binding:
            _fail(
                "CONTRACT_MISMATCH",
                f"bound completion cannot target an unbound manifest child: {completion.child_id}",
            )

        result = self
        if current.status is ChildLifecycle.PLANNED:
            result = result.record_transition(completion.child_id, ChildLifecycle.DISPATCHED)
        if result.child(completion.child_id).status is ChildLifecycle.DISPATCHED:
            result = result.record_transition(completion.child_id, ChildLifecycle.RUNNING)
        return result.record_transition(
            completion.child_id,
            completion.lifecycle,
            result_ref=completion.result_ref,
            result_digest=completion.result_digest,
        )

    def retry_child(
        self,
        child_id: str,
        *,
        attempt_id: str,
        parent_attempt_id: str | None = None,
        lease_generation: int | None = None,
    ) -> "FanoutManifest":
        """Create a new child attempt while retaining prior terminal evidence."""
        current = self.child(child_id)
        normalized_attempt_id = _text(
            attempt_id,
            "attempt_id",
            max_bytes=MAX_IDENTIFIER_BYTES,
            identifier=True,
        )
        if normalized_attempt_id == current.attempt_id:
            _fail("ATTEMPT_REUSE", f"retry must create a new attempt: {current.child_id}")
        next_parent_attempt = (
            _optional_identifier(parent_attempt_id, "parent_attempt_id")
            if parent_attempt_id is not None
            else self.parent.attempt_id
        )
        next_lease_generation = (
            _non_negative_int(lease_generation, "lease_generation")
            if lease_generation is not None
            else self.parent.lease_generation
        )
        if next_parent_attempt is None or next_parent_attempt == "":
            _fail("SCHEMA_INVALID", "parent_attempt_id is required for a retry")
        generation_changed = (
            next_parent_attempt != self.parent.attempt_id
            or next_lease_generation != self.parent.lease_generation
        )
        parent = self.parent
        if generation_changed:
            parent = replace(
                self.parent,
                attempt_id=next_parent_attempt,
                lease_generation=next_lease_generation,
            )

        stale = list(self.stale_children)
        for prior in self.children:
            if not prior.status.is_terminal:
                continue
            stale_record = replace(prior, status=ChildLifecycle.STALE)
            key = (stale_record.child_id, stale_record.attempt_id)
            if not any((item.child_id, item.attempt_id) == key for item in stale):
                stale.append(stale_record)

        if generation_changed:
            children = tuple(
                replace(
                    prior,
                    attempt_id=(
                        normalized_attempt_id
                        if prior.child_id == current.child_id
                        else f"{next_parent_attempt}:{prior.child_id}"
                    ),
                    status=ChildLifecycle.PLANNED,
                    result_ref=None,
                    result_digest=None,
                    parent_attempt_id=next_parent_attempt if prior.has_parent_binding else None,
                    lease_generation=(
                        next_lease_generation if prior.has_parent_binding else None
                    ),
                )
                for prior in self.children
            )
        else:
            children = tuple(
                replace(
                    prior,
                    attempt_id=normalized_attempt_id,
                    status=ChildLifecycle.PLANNED,
                    result_ref=None,
                    result_digest=None,
                )
                if prior.child_id == current.child_id
                else prior
                for prior in self.children
            )
        return self._snapshot(
            children=children,
            parent=parent,
            stale_children=tuple(stale),
        )

    retry = retry_child
    new_attempt = retry_child

    def join_decision(self) -> ManifestJoinDecision:
        missing = tuple(
            child.child_id for child in self.children if not child.status.is_terminal
        )
        failed = tuple(
            child.child_id
            for child in self.children
            if child.status.is_terminal
            and child.status not in self.join_semantics.acceptable_terminal_states
        )
        if failed:
            status = JoinStatus.BLOCKED
        elif missing:
            status = JoinStatus.NOT_READY
        else:
            status = JoinStatus.READY
        return ManifestJoinDecision(
            status=status,
            manifest_id=self.manifest_id,
            manifest_version=self.manifest_version,
            manifest_digest=self.manifest_digest,
            missing_child_ids=missing,
            failed_child_ids=failed,
        )

    def parent_result_binding(self) -> dict[str, Any]:
        decision = self.join_decision()
        if decision.status is JoinStatus.NOT_READY:
            _fail("JOIN_NOT_READY", "current manifest has non-terminal children")
        if decision.status is JoinStatus.BLOCKED:
            _fail("JOIN_BLOCKED", "current manifest contains a non-acceptable terminal child")
        evidence = [
            {
                "child_id": child.child_id,
                "result_ref": child.result_ref,
                "result_digest": child.result_digest,
            }
            for child in self.children
        ]
        evidence_digest = canonical_digest(
            {
                "manifest_id": self.manifest_id,
                "manifest_version": self.manifest_version,
                "manifest_digest": self.manifest_digest,
                "evidence": evidence,
            }
        )
        return {
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "manifest_digest": self.manifest_digest,
            "input_manifest_digest": self.manifest_digest,
            "join_semantics": self.join_semantics.to_dict(),
            "consumed_child_ids": [child.child_id for child in self.children],
            "consumed_evidence": evidence,
            "consumed_evidence_digest": evidence_digest,
        }


__all__ = [
    "DEFAULT_CHILD_TIMEOUT_SECONDS",
    "FANOUT_MANIFEST_PROTOCOL",
    "FanoutManifest",
    "FanoutManifestChild",
    "FanoutManifestError",
    "MANIFEST_VERSION",
    "ManifestJoinDecision",
    "ManifestParentIdentity",
    "MAX_MANIFEST_CHILDREN",
]
