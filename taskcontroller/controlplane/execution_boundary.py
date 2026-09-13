"""TC-MBX-306: executable Controller-owned execution boundary.

An :class:`ExecutionBoundary` is a pure capability envelope.  It describes the
maximum authority a Hermes execution may use; it does not dispatch a provider,
persist mailbox state, or grant any external authority.  Derived child
boundaries must pass :func:`prove_child_subset` before a caller may dispatch
one.

The boundary digest is a deterministic digest of the complete normalized
boundary *without* the digest field itself.  ``mbx-tc-307`` is responsible for
binding this digest into mailbox requests, child contracts, attempts, and
terminal results; this module intentionally stops at the boundary contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from taskcontroller.errors import TaskControllerValidationError


REPLAN_REQUIRED = "REPLAN_REQUIRED"
SCHEMA_INVALID = "SCHEMA_INVALID"
DIGEST_MISMATCH = "DIGEST_MISMATCH"

_MAX_ACTIONS = 64
_MAX_TARGETS = 64
_MAX_SOURCE_ROOTS = 64
_MAX_REPLAN_TRIGGERS = 64
_MAX_CHILDREN = 64
_MAX_PARALLEL = 64
_MAX_DEPTH = 8
MAX_TIME_BUDGET_SECONDS = 3_600
MAX_TOKEN_BUDGET = 1_000_000
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BOUNDARY_FIELDS = (
    "allowed_actions",
    "denied_actions",
    "writable_targets",
    "source_roots",
    "max_children",
    "max_parallel",
    "max_depth",
    "replan_required_when",
)
_OPTIONAL_BOUNDARY_FIELDS = (
    "time_budget_seconds",
    "token_budget",
)
_SUBSET_CHECKS = (
    "allowed_actions_subset",
    "denied_actions_preserved",
    "writable_targets_subset",
    "source_roots_subset",
    "child_budgets_within_parent",
    "replan_triggers_preserved",
)


class ExecutionBoundaryValidationError(TaskControllerValidationError):
    """Fail-closed boundary or child-subset validation error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        failed_checks: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.failed_checks = tuple(failed_checks)
        super().__init__(f"{code}: {message}", errors=list(self.failed_checks))


# A shorter name is useful to callers while retaining the descriptive class.
ExecutionBoundaryError = ExecutionBoundaryValidationError


def _fail(
    code: str,
    message: str,
    *,
    failed_checks: tuple[str, ...] = (),
) -> NoReturn:
    raise ExecutionBoundaryValidationError(code, message, failed_checks=failed_checks)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _fail(SCHEMA_INVALID, f"{name} must be a non-empty string without surrounding whitespace")
    return value


def _string_sequence(
    value: Any,
    name: str,
    *,
    min_items: int,
    max_items: int,
    path_like: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        _fail(SCHEMA_INVALID, f"{name} must be an array of strings")
    try:
        items = list(value)
    except (TypeError, ValueError) as exc:
        _fail(SCHEMA_INVALID, f"{name} must be an array of strings: {exc}")
    if len(items) < min_items:
        _fail(SCHEMA_INVALID, f"{name} must contain at least {min_items} item(s)")
    if len(items) > max_items:
        _fail(SCHEMA_INVALID, f"{name} must contain at most {max_items} items")
    normalized = tuple(sorted(_string(item, f"{name}[]") for item in items))
    if len(set(normalized)) != len(normalized):
        _fail(SCHEMA_INVALID, f"{name} must not contain duplicates")
    if path_like:
        for item in normalized:
            _validate_scope_path(item, name)
    return normalized


def _validate_scope_path(value: str, name: str) -> None:
    """Reject ambiguous/traversal roots while retaining relative scope identity."""
    if value.startswith("/") or "\\" in value:
        _fail(SCHEMA_INVALID, f"{name}[] must be a relative forward-slash scope root")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        # A trailing ``/**`` is the one intentional empty-looking pattern; it
        # is represented by the final ``**`` segment, not by an empty segment.
        _fail(SCHEMA_INVALID, f"{name}[] contains an unsafe path segment")
    wildcard_positions = [index for index, part in enumerate(parts) if "*" in part]
    if wildcard_positions and wildcard_positions != [len(parts) - 1]:
        _fail(SCHEMA_INVALID, f"{name}[] supports only a trailing wildcard")
    if wildcard_positions and parts[-1] not in ("*", "**"):
        _fail(SCHEMA_INVALID, f"{name}[] contains an unsupported wildcard")


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(SCHEMA_INVALID, f"{name} must be an integer")
    if value < minimum or value > maximum:
        _fail(SCHEMA_INVALID, f"{name} must be between {minimum} and {maximum}")
    return value


def _optional_integer(
    value: Any,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    return _integer(value, name, minimum=minimum, maximum=maximum)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail(SCHEMA_INVALID, f"boundary is not canonical JSON: {exc}")
    raise AssertionError("_fail must raise")


def _digest_for(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _root_without_wildcard(value: str) -> tuple[str, str | None]:
    if value.endswith("/**"):
        return value[:-3], "**"
    if value.endswith("/*"):
        return value[:-2], "*"
    return value, None


def _path_is_within(child: str, parent: str) -> bool:
    """Return whether one relative scope root is contained by another.

    Exact roots are treated as directory/business-target roots.  A trailing
    ``/**`` covers all descendants, while ``/*`` covers exactly one descendant
    segment.  Segment-aware comparison prevents ``src-extra`` from being
    accepted as a child of ``src``.
    """
    if child == parent:
        return True
    child_root, child_wildcard = _root_without_wildcard(child)
    parent_root, parent_wildcard = _root_without_wildcard(parent)

    parent_parts = parent_root.split("/")
    child_parts = child_root.split("/")
    if child_parts[: len(parent_parts)] != parent_parts:
        return False
    remaining = child_parts[len(parent_parts) :]

    if not remaining:
        # A one-segment wildcard does not include its own parent root, and a
        # recursive child wildcard cannot be narrowed to a one-segment parent.
        if parent_wildcard == "*":
            return False
        return parent_wildcard in (None, "**")
    if parent_wildcard == "*":
        return len(remaining) == 1 and child_wildcard is None
    # An exact parent root and a ``/**`` parent both contain all descendants.
    return parent_wildcard in (None, "**")


def _any_root_contains(child: str, parents: tuple[str, ...]) -> bool:
    return any(_path_is_within(child, parent) for parent in parents)


@dataclass(frozen=True)
class BoundarySubsetProof:
    """Machine-readable proof that a child boundary narrows its parent."""

    parent_scope_digest: str
    child_scope_digest: str
    checks: tuple[str, ...] = _SUBSET_CHECKS
    valid: bool = True

    def __post_init__(self) -> None:
        if not self.valid:
            raise ValueError("a BoundarySubsetProof must represent a valid proof")
        if self.checks != _SUBSET_CHECKS:
            raise ValueError("subset proof checks must cover every boundary dimension")

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "parent_scope_digest": self.parent_scope_digest,
            "child_scope_digest": self.child_scope_digest,
            "checks": list(self.checks),
        }


@dataclass(frozen=True)
class ExecutionBoundary:
    """Controller-owned maximum authority for one execution boundary.

    Constructor sequences are normalized to sorted tuples and all limits are
    explicit.  ``scope_digest`` is computed from the normalized boundary when
    omitted; a supplied value must match exactly.
    """

    allowed_actions: tuple[str, ...]
    denied_actions: tuple[str, ...]
    writable_targets: tuple[str, ...]
    source_roots: tuple[str, ...]
    max_children: int
    max_parallel: int
    max_depth: int
    replan_required_when: tuple[str, ...]
    scope_digest: str | None = None
    time_budget_seconds: int | None = None
    token_budget: int | None = None

    def __post_init__(self) -> None:
        normalized: dict[str, Any] = {
            "allowed_actions": _string_sequence(
                self.allowed_actions,
                "allowed_actions",
                min_items=1,
                max_items=_MAX_ACTIONS,
            ),
            "denied_actions": _string_sequence(
                self.denied_actions,
                "denied_actions",
                min_items=0,
                max_items=_MAX_ACTIONS,
            ),
            "writable_targets": _string_sequence(
                self.writable_targets,
                "writable_targets",
                min_items=0,
                max_items=_MAX_TARGETS,
                path_like=True,
            ),
            "source_roots": _string_sequence(
                self.source_roots,
                "source_roots",
                min_items=1,
                max_items=_MAX_SOURCE_ROOTS,
                path_like=True,
            ),
            "replan_required_when": _string_sequence(
                self.replan_required_when,
                "replan_required_when",
                min_items=1,
                max_items=_MAX_REPLAN_TRIGGERS,
            ),
        }
        overlap = sorted(set(normalized["allowed_actions"]) & set(normalized["denied_actions"]))
        if overlap:
            _fail(SCHEMA_INVALID, "allowed_actions and denied_actions overlap: " + ", ".join(overlap))
        for name, minimum, maximum in (
            ("max_children", 0, _MAX_CHILDREN),
            ("max_parallel", 1, _MAX_PARALLEL),
            ("max_depth", 0, _MAX_DEPTH),
        ):
            normalized[name] = _integer(getattr(self, name), name, minimum=minimum, maximum=maximum)
        normalized["time_budget_seconds"] = _optional_integer(
            self.time_budget_seconds,
            "time_budget_seconds",
            minimum=1,
            maximum=MAX_TIME_BUDGET_SECONDS,
        )
        normalized["token_budget"] = _optional_integer(
            self.token_budget,
            "token_budget",
            minimum=1,
            maximum=MAX_TOKEN_BUDGET,
        )
        for name, value in normalized.items():
            object.__setattr__(self, name, value)

        canonical = self._payload_without_digest()
        expected = _digest_for(canonical)
        supplied = self.scope_digest
        if supplied is not None:
            _string(supplied, "scope_digest")
            if not _DIGEST_RE.fullmatch(supplied):
                _fail(SCHEMA_INVALID, "scope_digest must match sha256:<64 lowercase hex>")
            if supplied != expected:
                _fail(DIGEST_MISMATCH, f"scope_digest does not match canonical boundary; expected {expected}")
        object.__setattr__(self, "scope_digest", expected)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionBoundary":
        """Parse a strict machine boundary mapping without mutating it."""
        if not isinstance(payload, Mapping):
            _fail(SCHEMA_INVALID, "execution boundary must be an object")
        candidate = dict(payload)
        expected_keys = (
            set(_BOUNDARY_FIELDS)
            | set(_OPTIONAL_BOUNDARY_FIELDS)
            | {"scope_digest"}
        )
        unknown = sorted(set(candidate) - expected_keys)
        if unknown:
            _fail(SCHEMA_INVALID, "unsupported execution boundary fields: " + ", ".join(unknown))
        missing = [field for field in _BOUNDARY_FIELDS if field not in candidate]
        if missing:
            _fail(SCHEMA_INVALID, "execution boundary is missing: " + ", ".join(missing))
        for field in _OPTIONAL_BOUNDARY_FIELDS:
            candidate.setdefault(field, None)
        return cls(**candidate)

    def _payload_without_digest(self) -> dict[str, Any]:
        return {
            "allowed_actions": list(self.allowed_actions),
            "denied_actions": list(self.denied_actions),
            "writable_targets": list(self.writable_targets),
            "source_roots": list(self.source_roots),
            "max_children": self.max_children,
            "max_parallel": self.max_parallel,
            "max_depth": self.max_depth,
            "replan_required_when": list(self.replan_required_when),
            "time_budget_seconds": self.time_budget_seconds,
            "token_budget": self.token_budget,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload_without_digest()
        payload["scope_digest"] = self.scope_digest
        return payload

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self._payload_without_digest())

    def digest(self) -> str:
        return cast(str, self.scope_digest)

    @property
    def boundary_digest(self) -> str:
        """Compatibility name for the later mailbox identity binding."""
        return self.digest()

    @property
    def source_scope_digest(self) -> str:
        """Explicit name for the digest covering source roots plus scope."""
        return self.digest()

    def validate_child_subset(
        self,
        child: "ExecutionBoundary",
        *,
        child_depth: int = 0,
    ) -> BoundarySubsetProof:
        """Prove that ``child`` cannot exceed this boundary.

        ``child_depth`` is the number of nested fan-out levels consumed by the
        derived contract.  The default checks ordinary field-wise subset
        semantics; callers creating a direct nested fan-out child pass ``1``
        so the remaining depth budget is enforced mechanically.
        """
        if not isinstance(child, ExecutionBoundary):
            _fail(SCHEMA_INVALID, "child execution boundary must be an ExecutionBoundary")
        if isinstance(child_depth, bool) or not isinstance(child_depth, int) or child_depth < 0:
            _fail(SCHEMA_INVALID, "child_depth must be an integer >= 0")

        failed: list[str] = []
        if not set(child.allowed_actions).issubset(self.allowed_actions):
            failed.append("allowed_actions_subset")
        if not set(self.denied_actions).issubset(child.denied_actions):
            failed.append("denied_actions_preserved")
        if not all(_any_root_contains(target, self.writable_targets) for target in child.writable_targets):
            failed.append("writable_targets_subset")
        if not all(_any_root_contains(root, self.source_roots) for root in child.source_roots):
            failed.append("source_roots_subset")

        remaining_depth = self.max_depth - child_depth
        budget_failed = False
        if child.max_children > self.max_children:
            failed.append("max_children")
            budget_failed = True
        if child.max_parallel > self.max_parallel:
            failed.append("max_parallel")
            budget_failed = True
        if child.max_depth > remaining_depth:
            failed.append("max_depth")
            budget_failed = True
        for budget_name in ("time_budget_seconds", "token_budget"):
            parent_budget = getattr(self, budget_name)
            child_budget = getattr(child, budget_name)
            if parent_budget is not None and (
                child_budget is None or child_budget > parent_budget
            ):
                budget_failed = True
        if budget_failed:
            failed.append("child_budgets_within_parent")
        if not set(self.replan_required_when).issubset(child.replan_required_when):
            failed.append("replan_triggers_preserved")

        if failed:
            _fail(
                REPLAN_REQUIRED,
                "child execution boundary is not a subset of the parent boundary",
                failed_checks=tuple(failed),
            )
        return BoundarySubsetProof(
            parent_scope_digest=self.digest(),
            child_scope_digest=child.digest(),
        )

    def validate_child(self, child: "ExecutionBoundary", *, child_depth: int = 0) -> BoundarySubsetProof:
        """Descriptive alias for :meth:`validate_child_subset`."""
        return self.validate_child_subset(child, child_depth=child_depth)

    def is_subset_of(self, parent: "ExecutionBoundary", *, child_depth: int = 0) -> bool:
        """Return a boolean for read-only callers without hiding malformed input."""
        if not isinstance(parent, ExecutionBoundary):
            _fail(SCHEMA_INVALID, "parent execution boundary must be an ExecutionBoundary")
        try:
            parent.validate_child_subset(self, child_depth=child_depth)
        except ExecutionBoundaryValidationError as exc:
            if exc.code == REPLAN_REQUIRED:
                return False
            raise
        return True


def prove_child_subset(
    parent: ExecutionBoundary,
    child: ExecutionBoundary,
    *,
    child_depth: int = 0,
) -> BoundarySubsetProof:
    """Pure function form of :meth:`ExecutionBoundary.validate_child_subset`."""
    if not isinstance(parent, ExecutionBoundary):
        _fail(SCHEMA_INVALID, "parent execution boundary must be an ExecutionBoundary")
    return parent.validate_child_subset(child, child_depth=child_depth)


def validate_child_subset(
    parent: ExecutionBoundary,
    child: ExecutionBoundary,
    *,
    child_depth: int = 0,
) -> BoundarySubsetProof:
    """Module-level alias for callers that prefer validator terminology."""
    return prove_child_subset(parent, child, child_depth=child_depth)


__all__ = [
    "BoundarySubsetProof",
    "DIGEST_MISMATCH",
    "ExecutionBoundary",
    "ExecutionBoundaryError",
    "ExecutionBoundaryValidationError",
    "REPLAN_REQUIRED",
    "SCHEMA_INVALID",
    "prove_child_subset",
    "validate_child_subset",
]
