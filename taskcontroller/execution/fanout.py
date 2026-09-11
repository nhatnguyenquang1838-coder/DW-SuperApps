"""TC-MBX-504 provider-neutral bounded fan-out coordination.

This module is a planning/state-normalization seam only.  It does not invoke a
provider, persist a manifest/mailbox event, or enable runtime fan-out.  A
Controller-owned parent contract supplies the execution budget; immutable child
completion references advance an in-memory coordinator snapshot.  The join
input is always normalized by stable child identity, never by arrival order.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias

from taskcontroller.execution.child_contract import ChildContract, ParentContract


FANOUT_COORDINATOR_PROTOCOL = "dw.taskcontroller.fanout-coordinator/v1"
MAX_FANOUT_CHILDREN = 64
MAX_FANOUT_PARALLEL = 64
MAX_STAGE_COUNT = 64
MAX_CHILD_ID_LENGTH = 128
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

ParentInput: TypeAlias = ParentContract | Mapping[str, Any]
ChildInput: TypeAlias = ChildContract | Mapping[str, Any]


class FanoutCoordinatorError(ValueError):
    """Stable fail-closed error for fan-out plan/completion validation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class ChildLifecycleError(FanoutCoordinatorError):
    """Stable fail-closed error for an illegal child lifecycle transition."""


class FanoutMode(str, Enum):
    """Execution topology inside one Controller-approved parent boundary."""

    PARALLEL = "PARALLEL"
    STAGED = "STAGED"


class ChildLifecycle(str, Enum):
    """Normative lifecycle for one bounded child execution attempt."""

    PLANNED = "PLANNED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    STALE = "STALE"

    @property
    def is_terminal(self) -> bool:
        return self in _CHILD_LIFECYCLE_TERMINAL_STATES

    @classmethod
    def non_terminal_states(cls) -> tuple["ChildLifecycle", ...]:
        return _CHILD_LIFECYCLE_NON_TERMINAL_STATES

    @classmethod
    def terminal_states(cls) -> tuple["ChildLifecycle", ...]:
        return _CHILD_LIFECYCLE_TERMINAL_STATES


_CHILD_LIFECYCLE_NON_TERMINAL_STATES = (
    ChildLifecycle.PLANNED,
    ChildLifecycle.DISPATCHED,
    ChildLifecycle.RUNNING,
)
_CHILD_LIFECYCLE_TERMINAL_STATES = (
    ChildLifecycle.SUCCEEDED,
    ChildLifecycle.FAILED,
    ChildLifecycle.TIMED_OUT,
    ChildLifecycle.CANCELLED,
    ChildLifecycle.STALE,
)
_CHILD_LIFECYCLE_TRANSITIONS = {
    ChildLifecycle.PLANNED: frozenset(
        {ChildLifecycle.DISPATCHED, ChildLifecycle.CANCELLED, ChildLifecycle.STALE}
    ),
    ChildLifecycle.DISPATCHED: frozenset(
        {
            ChildLifecycle.RUNNING,
            ChildLifecycle.TIMED_OUT,
            ChildLifecycle.CANCELLED,
            ChildLifecycle.STALE,
        }
    ),
    ChildLifecycle.RUNNING: frozenset(
        {
            ChildLifecycle.SUCCEEDED,
            ChildLifecycle.FAILED,
            ChildLifecycle.TIMED_OUT,
            ChildLifecycle.CANCELLED,
            ChildLifecycle.STALE,
        }
    ),
    ChildLifecycle.SUCCEEDED: frozenset(),
    ChildLifecycle.FAILED: frozenset(),
    ChildLifecycle.TIMED_OUT: frozenset(),
    ChildLifecycle.CANCELLED: frozenset(),
    ChildLifecycle.STALE: frozenset(),
}


class JoinPolicy(str, Enum):
    """MVP join policy; richer partial/quorum policy belongs to later slices."""

    ALL_REQUIRED = "ALL_REQUIRED"


class JoinStatus(str, Enum):
    """Explicit parent join decision."""

    NOT_READY = "NOT_READY"
    READY = "READY"
    BLOCKED = "BLOCKED"


class CompletionStatus(str, Enum):
    """Terminal outcomes understood by this coordinator.

    ``SUCCEEDED`` is the only outcome that can satisfy ``ALL_REQUIRED``.
    Other terminal outcomes remain in the normalized evidence set and block
    the parent rather than being silently dropped.
    """

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    STALE = "STALE"

    @property
    def lifecycle(self) -> ChildLifecycle:
        return ChildLifecycle(self.value)


_TERMINAL_STATUSES = frozenset(CompletionStatus)


@dataclass(frozen=True, slots=True)
class JoinSemantics:
    """Normative acceptance/failure grammar for a parent join.

    ``ALL_REQUIRED`` is intentionally strict: only successful terminal child
    outcomes are acceptable. Missing children remain ``NOT_READY``; any
    failure, timeout, cancellation or stale child blocks the parent. Partial
    results are retained as evidence but never treated as a successful join.
    """

    policy: JoinPolicy | str
    acceptable_terminal_states: tuple[CompletionStatus | str, ...]
    partial_result_policy: str = "NOT_READY"
    failure_policy: str = "BLOCK_PARENT"
    timeout_policy: str = "BLOCK_PARENT"
    cancellation_policy: str = "BLOCK_PARENT"
    stale_policy: str = "BLOCK_PARENT"

    @classmethod
    def for_policy(cls, policy: JoinPolicy | str) -> "JoinSemantics":
        return cls(
            policy=policy,
            acceptable_terminal_states=(CompletionStatus.SUCCEEDED,),
        )

    def __post_init__(self) -> None:
        selected_policy = _enum(self.policy, JoinPolicy, "join_policy")
        states = tuple(
            _enum(item, CompletionStatus, "acceptable_terminal_states[]")
            for item in self.acceptable_terminal_states
        )
        expected = (CompletionStatus.SUCCEEDED,)
        if selected_policy is not JoinPolicy.ALL_REQUIRED or states != expected:
            _fail(
                "SCHEMA_INVALID",
                "ALL_REQUIRED accepts exactly SUCCEEDED terminal children",
            )
        policies = (
            "partial_result_policy",
            "failure_policy",
            "timeout_policy",
            "cancellation_policy",
            "stale_policy",
        )
        for name in policies:
            value = getattr(self, name)
            if value not in {"NOT_READY", "BLOCK_PARENT"}:
                _fail("SCHEMA_INVALID", f"{name} has an unsupported disposition")
        if self.partial_result_policy != "NOT_READY":
            _fail("SCHEMA_INVALID", "ALL_REQUIRED partial_result_policy must be NOT_READY")
        if any(
            getattr(self, name) != "BLOCK_PARENT"
            for name in (
                "failure_policy",
                "timeout_policy",
                "cancellation_policy",
                "stale_policy",
            )
        ):
            _fail("SCHEMA_INVALID", "ALL_REQUIRED non-success terminal policy must BLOCK_PARENT")
        object.__setattr__(self, "policy", selected_policy)
        object.__setattr__(self, "acceptable_terminal_states", expected)

    @property
    def allow_partial(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.value,
            "acceptable_terminal_states": [item.value for item in self.acceptable_terminal_states],
            "allow_partial": self.allow_partial,
            "partial_result_policy": self.partial_result_policy,
            "failure_policy": self.failure_policy,
            "timeout_policy": self.timeout_policy,
            "cancellation_policy": self.cancellation_policy,
            "stale_policy": self.stale_policy,
        }


def _fail(code: str, message: str) -> None:
    raise FanoutCoordinatorError(code, message)


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


def _sequence(value: Any, name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        _fail("SCHEMA_INVALID", f"{name} must be an array")
    try:
        return tuple(value)
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"{name} must be an array: {exc}")
    raise AssertionError("_fail must raise")


def _enum(value: Any, enum_type: type[Enum], name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        _fail("SCHEMA_INVALID", f"{name} must be one of {allowed}: {exc}")
    raise AssertionError("_fail must raise")


def allowed_child_lifecycle_transitions(
    current: ChildLifecycle | str,
) -> tuple[ChildLifecycle, ...]:
    """Return the only non-idempotent next states allowed from ``current``."""
    selected = _enum(current, ChildLifecycle, "current_lifecycle")
    return tuple(
        state for state in ChildLifecycle if state in _CHILD_LIFECYCLE_TRANSITIONS[selected]
    )


def transition_child_lifecycle(
    current: ChildLifecycle | str,
    target: ChildLifecycle | str,
) -> ChildLifecycle:
    """Apply one bounded lifecycle transition, allowing exact replay only."""
    selected_current = _enum(current, ChildLifecycle, "current_lifecycle")
    selected_target = _enum(target, ChildLifecycle, "target_lifecycle")
    if selected_current is selected_target:
        return selected_current
    if selected_target not in _CHILD_LIFECYCLE_TRANSITIONS[selected_current]:
        raise ChildLifecycleError(
            "INVALID_LIFECYCLE_TRANSITION",
            f"{selected_current.value} -> {selected_target.value} is not allowed",
        )
    return selected_target


@dataclass(frozen=True, slots=True)
class ChildLifecycleState:
    """Immutable child lifecycle snapshot with fail-closed transitions."""

    child_id: str
    state: ChildLifecycle | str = ChildLifecycle.PLANNED

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "child_id",
            _text(self.child_id, "child_id", max_bytes=MAX_CHILD_ID_LENGTH, identifier=True),
        )
        object.__setattr__(self, "state", _enum(self.state, ChildLifecycle, "state"))

    def transition(self, target: ChildLifecycle | str) -> "ChildLifecycleState":
        next_state = transition_child_lifecycle(self.state, target)
        if next_state is self.state:
            return self
        return ChildLifecycleState(child_id=self.child_id, state=next_state)

    def to_dict(self) -> dict[str, str]:
        return {"child_id": self.child_id, "state": self.state.value}


@dataclass(frozen=True, slots=True)
class ChildLifecycleTransition:
    """Validated state-to-state transition record for durable adapters."""

    from_state: ChildLifecycle | str
    to_state: ChildLifecycle | str

    def __post_init__(self) -> None:
        current = _enum(self.from_state, ChildLifecycle, "from_state")
        target = transition_child_lifecycle(current, self.to_state)
        object.__setattr__(self, "from_state", current)
        object.__setattr__(self, "to_state", target)

    @property
    def idempotent_replay(self) -> bool:
        return self.from_state is self.to_state

    def to_dict(self) -> dict[str, str]:
        return {"from_state": self.from_state.value, "to_state": self.to_state.value}



def _canonical_digest(payload: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"fan-out payload is not canonical JSON: {exc}")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _child(value: ChildInput) -> ChildContract:
    if isinstance(value, ChildContract):
        return value
    if isinstance(value, Mapping):
        try:
            return ChildContract.from_dict(value)
        except Exception as exc:
            _fail("SCHEMA_INVALID", f"child contract is invalid: {exc}")
    _fail("SCHEMA_INVALID", "children must contain ChildContract values")
    raise AssertionError("_fail must raise")


def _parent(value: ParentInput) -> ParentContract:
    if isinstance(value, ParentContract):
        return value
    if isinstance(value, Mapping):
        try:
            return ParentContract.from_mapping(value)
        except Exception as exc:
            _fail("SCHEMA_INVALID", f"parent contract is invalid: {exc}")
    _fail("SCHEMA_INVALID", "parent must be a ParentContract or object")
    raise AssertionError("_fail must raise")


def _parent_binding(parent: ParentContract) -> dict[str, Any]:
    return {
        "run_id": parent.run_id,
        "node_id": parent.node_id,
        "contract_id": parent.contract_id,
        "contract_digest": parent.contract_digest,
        "plan_version": parent.plan_version,
        "boundary_digest": parent.boundary.digest(),
        "source_digest": parent.source_digest,
        "source_manifest_ref": parent.source_manifest_ref,
        "source_manifest_digest": parent.source_manifest["digest"],
        "standards_profile_ref": parent.standards_profile_ref,
        "standards_profile_digest": parent.standards_profile["digest"],
    }


def _child_binding(child: ChildContract) -> dict[str, Any]:
    return {
        "run_id": child.run_id,
        "node_id": child.node_id,
        "contract_id": child.parent_contract_id,
        "contract_digest": child.parent_contract_digest,
        "plan_version": child.plan_version,
        "boundary_digest": child.parent_boundary_digest,
        "source_digest": child.source_digest,
        "source_manifest_ref": child.source_manifest_ref,
        "source_manifest_digest": child.source_manifest["digest"],
        "standards_profile_ref": child.standards_profile_ref,
        "standards_profile_digest": child.standards_profile["digest"],
    }


def _assert_child_belongs(parent: ParentContract, child: ChildContract) -> None:
    expected = _parent_binding(parent)
    actual = _child_binding(child)
    mismatches = tuple(
        key for key in expected if expected[key] != actual.get(key)
    )
    if mismatches:
        _fail(
            "CONTRACT_MISMATCH",
            "child is not bound to the supplied parent: " + ", ".join(mismatches),
        )


@dataclass(frozen=True, slots=True)
class ChildCompletion:
    """Immutable, reference-only terminal child completion.

    The coordinator accepts no raw provider payload.  Both result references
    and their digests are required so a future durable adapter can bind this
    record without treating arrival order or hidden transcript text as state.
    """

    child_id: str
    child_contract_digest: str
    status: CompletionStatus | str
    result_ref: str
    result_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "child_id",
            _text(self.child_id, "child_id", max_bytes=MAX_CHILD_ID_LENGTH, identifier=True),
        )
        object.__setattr__(
            self,
            "child_contract_digest",
            _digest(self.child_contract_digest, "child_contract_digest"),
        )
        object.__setattr__(self, "status", _enum(self.status, CompletionStatus, "status"))
        object.__setattr__(
            self,
            "result_ref",
            _text(self.result_ref, "result_ref", max_bytes=1024),
        )
        object.__setattr__(self, "result_digest", _digest(self.result_digest, "result_digest"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "child_contract_digest": self.child_contract_digest,
            "status": self.status.value,
            "result_ref": self.result_ref,
            "result_digest": self.result_digest,
        }

    @property
    def lifecycle(self) -> ChildLifecycle:
        return self.status.lifecycle


# Function form is convenient for adapters and keeps constructor validation in
# one immutable type.
def child_completion(
    *,
    child_id: str,
    child_contract_digest: str,
    status: CompletionStatus | str,
    result_ref: str,
    result_digest: str,
) -> ChildCompletion:
    return ChildCompletion(
        child_id=child_id,
        child_contract_digest=child_contract_digest,
        status=status,
        result_ref=result_ref,
        result_digest=result_digest,
    )


@dataclass(frozen=True, slots=True)
class FanoutPlan:
    """Digest-bound deterministic child waves under one parent contract."""

    parent_contract_id: str
    parent_contract_digest: str
    parent_boundary_digest: str
    run_id: str
    node_id: str
    plan_version: str
    children: tuple[ChildContract, ...]
    mode: FanoutMode
    max_parallel: int
    join_policy: JoinPolicy
    stages: tuple[tuple[str, ...], ...]
    plan_digest: str

    @classmethod
    def from_parent(
        cls,
        parent: ParentInput,
        children: Sequence[ChildInput],
        *,
        mode: FanoutMode | str = FanoutMode.PARALLEL,
        max_parallel: int | None = None,
        stages: Sequence[Sequence[str]] | None = None,
        join_policy: JoinPolicy | str = JoinPolicy.ALL_REQUIRED,
    ) -> "FanoutPlan":
        bound_parent = _parent(parent)
        items = tuple(_child(item) for item in _sequence(children, "children"))
        if not items:
            _fail("SCHEMA_INVALID", "children must contain at least one item")
        if len(items) > MAX_FANOUT_CHILDREN:
            _fail("REPLAN_REQUIRED", "children exceed bounded fan-out count")
        if len(items) > bound_parent.boundary.max_children:
            _fail("REPLAN_REQUIRED", "children exceed parent max_children")
        for item in items:
            _assert_child_belongs(bound_parent, item)
        ids = tuple(item.child_id for item in items)
        if len(set(ids)) != len(ids):
            _fail("SCHEMA_INVALID", "children must contain each child_id exactly once")

        selected_mode = _enum(mode, FanoutMode, "mode")
        selected_join = _enum(join_policy, JoinPolicy, "join_policy")
        join_semantics = JoinSemantics.for_policy(selected_join)  # type: ignore[arg-type]
        requested_parallel = (
            bound_parent.boundary.max_parallel if max_parallel is None else max_parallel
        )
        if (
            isinstance(requested_parallel, bool)
            or not isinstance(requested_parallel, int)
            or not 1 <= requested_parallel <= MAX_FANOUT_PARALLEL
        ):
            _fail("SCHEMA_INVALID", "max_parallel must be an integer between 1 and 64")
        if requested_parallel > bound_parent.boundary.max_parallel:
            _fail("REPLAN_REQUIRED", "max_parallel exceeds parent max_parallel")

        normalized_stages = cls._normalize_stages(
            ids,
            selected_mode,
            requested_parallel,
            stages,
        )
        payload = {
            "protocol": FANOUT_COORDINATOR_PROTOCOL,
            "parent": _parent_binding(bound_parent),
            "children": [
                {"child_id": item.child_id, "contract_digest": item.contract_digest}
                for item in items
            ],
            "mode": selected_mode.value,
            "max_parallel": requested_parallel,
            "join_policy": selected_join.value,
            "join_semantics": join_semantics.to_dict(),
            "stages": [list(stage) for stage in normalized_stages],
        }
        return cls(
            parent_contract_id=bound_parent.contract_id,
            parent_contract_digest=bound_parent.contract_digest,
            parent_boundary_digest=bound_parent.boundary.digest(),
            run_id=bound_parent.run_id,
            node_id=bound_parent.node_id,
            plan_version=bound_parent.plan_version,
            children=items,
            mode=selected_mode,  # type: ignore[arg-type]
            max_parallel=requested_parallel,
            join_policy=selected_join,  # type: ignore[arg-type]
            stages=normalized_stages,
            plan_digest=_canonical_digest(payload),
        )

    @classmethod
    def _normalize_stages(
        cls,
        child_ids: tuple[str, ...],
        mode: FanoutMode,
        max_parallel: int,
        stages: Sequence[Sequence[str]] | None,
    ) -> tuple[tuple[str, ...], ...]:
        if mode is FanoutMode.PARALLEL:
            if stages is not None:
                _fail("SCHEMA_INVALID", "stages are only supplied for STAGED mode")
            return tuple(
                tuple(child_ids[index : index + max_parallel])
                for index in range(0, len(child_ids), max_parallel)
            )

        if stages is None:
            _fail("SCHEMA_INVALID", "STAGED mode requires explicit stages")
        raw_stages = _sequence(stages, "stages")
        if not raw_stages or len(raw_stages) > MAX_STAGE_COUNT:
            _fail("SCHEMA_INVALID", "stages must contain between 1 and 64 items")
        expected = set(child_ids)
        seen: list[str] = []
        result: list[tuple[str, ...]] = []
        for index, raw_stage in enumerate(raw_stages):
            stage = tuple(
                _text(item, f"stages[{index}][]", max_bytes=MAX_CHILD_ID_LENGTH, identifier=True)
                for item in _sequence(raw_stage, f"stages[{index}]")
            )
            if not stage:
                _fail("SCHEMA_INVALID", f"stages[{index}] must not be empty")
            if len(stage) > max_parallel:
                _fail("REPLAN_REQUIRED", "a staged dispatch window exceeds max_parallel")
            if len(set(stage)) != len(stage):
                _fail("SCHEMA_INVALID", "each staged child_id must occur exactly once")
            unknown = sorted(set(stage) - expected)
            if unknown:
                _fail("CONTRACT_MISMATCH", "staged children are unknown: " + ", ".join(unknown))
            seen.extend(stage)
            result.append(stage)
        if set(seen) != expected or len(seen) != len(expected):
            _fail("SCHEMA_INVALID", "stages must account for every child_id exactly once")
        return tuple(result)

    @property
    def join_semantics(self) -> JoinSemantics:
        return JoinSemantics.for_policy(self.join_policy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": FANOUT_COORDINATOR_PROTOCOL,
            "parent_contract_id": self.parent_contract_id,
            "parent_contract_digest": self.parent_contract_digest,
            "parent_boundary_digest": self.parent_boundary_digest,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "plan_version": self.plan_version,
            "children": [
                {"child_id": child.child_id, "contract_digest": child.contract_digest}
                for child in self.children
            ],
            "mode": self.mode.value,
            "max_parallel": self.max_parallel,
            "join_policy": self.join_policy.value,
            "join_semantics": self.join_semantics.to_dict(),
            "stages": [list(stage) for stage in self.stages],
            "plan_digest": self.plan_digest,
        }


@dataclass(frozen=True, slots=True)
class NormalizedJoinInput:
    """Canonical, completion-order-independent input for a future Mixer."""

    parent_contract_id: str
    parent_contract_digest: str
    plan_digest: str
    child_ids: tuple[str, ...]
    completions: tuple[ChildCompletion, ...]
    digest: str

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.completions, key=lambda item: item.child_id))
        if tuple(item.child_id for item in ordered) != tuple(sorted(self.child_ids)):
            _fail("SCHEMA_INVALID", "normalized child_ids do not match completions")
        object.__setattr__(self, "completions", ordered)
        object.__setattr__(self, "child_ids", tuple(item.child_id for item in ordered))
        payload = {
            "parent_contract_id": self.parent_contract_id,
            "parent_contract_digest": self.parent_contract_digest,
            "plan_digest": self.plan_digest,
            "completions": [item.to_dict() for item in ordered],
        }
        expected = _canonical_digest(payload)
        supplied = _digest(self.digest, "digest")
        if supplied != expected:
            _fail("DIGEST_MISMATCH", "normalized join digest does not match canonical input")
        object.__setattr__(self, "digest", expected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_contract_id": self.parent_contract_id,
            "parent_contract_digest": self.parent_contract_digest,
            "plan_digest": self.plan_digest,
            "child_ids": list(self.child_ids),
            "completions": [item.to_dict() for item in self.completions],
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class JoinDecision:
    """Explicit join result; incomplete or failed inputs are never omitted."""

    status: JoinStatus
    normalized_input: NormalizedJoinInput
    missing_child_ids: tuple[str, ...]
    failed_child_ids: tuple[str, ...]
    join_semantics: JoinSemantics = JoinSemantics.for_policy(JoinPolicy.ALL_REQUIRED)

    @property
    def ready(self) -> bool:
        return self.status is JoinStatus.READY

    @property
    def input(self) -> NormalizedJoinInput:
        return self.normalized_input


@dataclass(frozen=True, slots=True)
class FanoutCoordinator:
    """Immutable coordinator snapshot for bounded waves and explicit join."""

    plan: FanoutPlan
    completions: tuple[ChildCompletion, ...] = ()

    def __post_init__(self) -> None:
        known = {child.child_id: child for child in self.plan.children}
        normalized: list[ChildCompletion] = []
        for completion in self.completions:
            if not isinstance(completion, ChildCompletion):
                _fail("SCHEMA_INVALID", "completions must contain ChildCompletion values")
            expected = known.get(completion.child_id)
            if expected is None:
                _fail("CONTRACT_MISMATCH", f"unknown child: {completion.child_id}")
            if completion.child_contract_digest != expected.contract_digest:
                _fail("CONTRACT_MISMATCH", f"child contract digest mismatch: {completion.child_id}")
            if completion.status not in _TERMINAL_STATUSES:
                _fail("SCHEMA_INVALID", "completion status must be terminal")
            normalized.append(completion)
        by_id: dict[str, ChildCompletion] = {}
        for completion in normalized:
            prior = by_id.get(completion.child_id)
            if prior is not None and prior != completion:
                _fail("CONTRACT_MISMATCH", f"conflicting completion: {completion.child_id}")
            by_id[completion.child_id] = completion
        object.__setattr__(
            self,
            "completions",
            tuple(by_id[child_id] for child_id in sorted(by_id)),
        )

    @classmethod
    def from_parent(
        cls,
        parent: ParentInput,
        children: Sequence[ChildInput],
        **kwargs: Any,
    ) -> "FanoutCoordinator":
        return cls(FanoutPlan.from_parent(parent, children, **kwargs))

    @classmethod
    def from_children(
        cls,
        children: Sequence[ChildInput],
        *,
        parent: ParentInput | None = None,
        mode: FanoutMode | str = FanoutMode.PARALLEL,
        max_parallel: int | None = None,
        stages: Sequence[Sequence[str]] | None = None,
        join_policy: JoinPolicy | str = JoinPolicy.ALL_REQUIRED,
    ) -> "FanoutCoordinator":
        if parent is None:
            _fail(
                "CONTRACT_MISMATCH",
                "parent contract is required to prove fan-out budget and identity",
            )
        return cls.from_parent(
            parent,
            children,
            mode=mode,
            max_parallel=max_parallel,
            stages=stages,
            join_policy=join_policy,
        )

    @property
    def child_contracts(self) -> tuple[ChildContract, ...]:
        return self.plan.children

    @property
    def completed_child_ids(self) -> tuple[str, ...]:
        return tuple(item.child_id for item in self.completions)

    @property
    def active_child_ids(self) -> tuple[str, ...]:
        return self.dispatch_window()

    def lifecycle_state(self, child_id: str) -> ChildLifecycle:
        """Project this snapshot into the normative child lifecycle."""
        known = {child.child_id for child in self.plan.children}
        if child_id not in known:
            _fail("CONTRACT_MISMATCH", f"unknown child: {child_id}")
        completion = next(
            (item for item in self.completions if item.child_id == child_id),
            None,
        )
        if completion is not None:
            return completion.lifecycle
        if child_id in self.dispatch_window():
            return ChildLifecycle.DISPATCHED
        return ChildLifecycle.PLANNED

    def lifecycle_states(self) -> dict[str, ChildLifecycle]:
        return {
            child.child_id: self.lifecycle_state(child.child_id)
            for child in self.plan.children
        }

    def dispatch_window(self) -> tuple[str, ...]:
        """Return only the current bounded window; later stages stay closed."""
        completed = {item.child_id: item for item in self.completions}
        for stage in self.plan.stages:
            stage_completions = [completed.get(child_id) for child_id in stage]
            if any(
                item is not None and item.status is not CompletionStatus.SUCCEEDED
                for item in stage_completions
            ):
                return ()
            remaining = tuple(child_id for child_id in stage if child_id not in completed)
            if remaining:
                return remaining
        return ()

    def complete(self, completion: ChildCompletion) -> "FanoutCoordinator":
        """Accept one current-window completion, or idempotently replay it."""
        if not isinstance(completion, ChildCompletion):
            _fail("SCHEMA_INVALID", "completion must be a ChildCompletion")
        known = {child.child_id: child for child in self.plan.children}
        expected = known.get(completion.child_id)
        if expected is None:
            _fail("CONTRACT_MISMATCH", f"unknown child: {completion.child_id}")
        if completion.child_contract_digest != expected.contract_digest:
            _fail("CONTRACT_MISMATCH", f"child contract digest mismatch: {completion.child_id}")
        prior = next(
            (item for item in self.completions if item.child_id == completion.child_id),
            None,
        )
        if prior is not None:
            if prior == completion:
                return self
            _fail("CONTRACT_MISMATCH", f"conflicting completion: {completion.child_id}")
        if completion.child_id not in self.dispatch_window():
            _fail(
                "CONTRACT_MISMATCH",
                f"child is not in the current dispatch window: {completion.child_id}",
            )
        return FanoutCoordinator(self.plan, self.completions + (completion,))

    # Descriptive aliases for adapters; all use the same immutable transition.
    record_completion = complete
    accept_completion = complete
    record_child_completion = complete

    def normalized_input(self) -> NormalizedJoinInput:
        ordered = tuple(sorted(self.completions, key=lambda item: item.child_id))
        payload = {
            "parent_contract_id": self.plan.parent_contract_id,
            "parent_contract_digest": self.plan.parent_contract_digest,
            "plan_digest": self.plan.plan_digest,
            "completions": [item.to_dict() for item in ordered],
        }
        return NormalizedJoinInput(
            parent_contract_id=self.plan.parent_contract_id,
            parent_contract_digest=self.plan.parent_contract_digest,
            plan_digest=self.plan.plan_digest,
            child_ids=tuple(item.child_id for item in ordered),
            completions=ordered,
            digest=_canonical_digest(payload),
        )

    def join(self) -> JoinDecision:
        """Evaluate the declared join grammar without dropping failures."""
        normalized = self.normalized_input()
        semantics = self.plan.join_semantics
        received = set(normalized.child_ids)
        expected = {child.child_id for child in self.plan.children}
        missing = tuple(sorted(expected - received))
        failed = tuple(
            item.child_id
            for item in normalized.completions
            if item.status not in semantics.acceptable_terminal_states
        )
        if failed:
            status = JoinStatus.BLOCKED
        elif missing:
            status = JoinStatus.NOT_READY
        else:
            status = JoinStatus.READY
        return JoinDecision(
            status=status,
            normalized_input=normalized,
            missing_child_ids=missing,
            failed_child_ids=tuple(sorted(failed)),
            join_semantics=semantics,
        )

    def join_decision(self) -> JoinDecision:
        return self.join()


# Plan-level aliases keep the seam discoverable without alternate behavior.
FanoutCoordinatorPlan = FanoutPlan
FanoutCompletion = ChildCompletion
NormalizedInputSet = NormalizedJoinInput


__all__ = [
    "ChildCompletion",
    "ChildLifecycle",
    "ChildLifecycleError",
    "ChildLifecycleState",
    "ChildLifecycleTransition",
    "CompletionStatus",
    "FANOUT_COORDINATOR_PROTOCOL",
    "FanoutCompletion",
    "FanoutCoordinator",
    "FanoutCoordinatorError",
    "FanoutCoordinatorPlan",
    "FanoutMode",
    "FanoutPlan",
    "JoinDecision",
    "JoinPolicy",
    "JoinSemantics",
    "JoinStatus",
    "MAX_FANOUT_CHILDREN",
    "MAX_FANOUT_PARALLEL",
    "MAX_STAGE_COUNT",
    "NormalizedInputSet",
    "NormalizedJoinInput",
    "allowed_child_lifecycle_transitions",
    "child_completion",
    "transition_child_lifecycle",
]
