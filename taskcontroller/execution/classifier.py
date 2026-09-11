"""TC-MBX-502 deterministic, bounded execution-classifier policy.

The policy consumes only explicit Controller-bound metadata and returns the
TC-MBX-501 normalized classification object.  It never creates child contracts,
selects an AgentInstance, dispatches work, or grants authority.  ``proposed``
child counts are advisory metadata and an explicitly supplied parent budget is
checked fail-closed rather than silently truncated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, NoReturn

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.classification import (
    MAX_PROPOSED_CHILD_COUNT,
    ExecutionClass,
    ExecutionClassification,
)


CLASSIFIER_POLICY_SCHEMA_VERSION = "dw.taskcontroller.classifier-policy/v1"

# The boundary is explicit and inclusive: a task at this size can remain
# atomic when every other atomic precondition is satisfied.  Larger artifacts
# are complex and may be chunked by a later bounded task.
ATOMIC_ARTIFACT_LIMIT_BYTES = 64 * 1024
MAX_ARTIFACT_SIZE_BYTES = 1024 * 1024 * 1024
MAX_ACCEPTANCE_CRITERIA = 64
MAX_ACCEPTANCE_CRITERION_LENGTH = 512
MAX_ACCEPTANCE_CRITERIA_BYTES = 16 * 1024
MAX_PARENT_CHILDREN = MAX_PROPOSED_CHILD_COUNT

DEFAULT_COMPLEX_LENSES = ("architecture", "implementation")
DEFAULT_REVIEW_LENSES = ("implementation", "testing")
DEFAULT_CROSS_REVIEW_LENSES = (
    "architecture",
    "implementation",
    "security",
    "testing",
)


class TaskShape(str, Enum):
    """Explicit shape supplied by the Controller-bound task descriptor."""

    ATOMIC = "ATOMIC"
    COMPLEX = "COMPLEX"
    REVIEW = "REVIEW"
    CROSS_REVIEW = "CROSS_REVIEW"


class ReviewMode(str, Enum):
    """Declared review mode; ``AUTO`` leaves shape/size rules in control."""

    AUTO = "AUTO"
    NONE = "NONE"
    REVIEW = "REVIEW"
    CROSS_REVIEW = "CROSS_REVIEW"


class ClassifierPolicyError(TaskControllerValidationError):
    """Fail-closed classifier input or parent-budget error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise ClassifierPolicyError(code, message)


def _normalized_choice(
    name: str,
    value: Any,
    enum_type: type[Enum],
    *,
    aliases: Mapping[str, str] | None = None,
) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        _fail("SCHEMA_INVALID", f"{name} must be a string")
    normalized = value.strip().upper().replace("-", "_")
    if aliases:
        normalized = aliases.get(normalized, normalized)
    try:
        return enum_type(normalized).value
    except ValueError:
        allowed = ", ".join(item.value for item in enum_type)
        _fail("SCHEMA_INVALID", f"{name} must be one of {allowed}")
    raise AssertionError("_fail must raise")


def _bounded_criteria(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail("SCHEMA_INVALID", "acceptance_criteria must be an array")
    if not value:
        _fail("SCHEMA_INVALID", "acceptance_criteria must contain at least one item")
    if len(value) > MAX_ACCEPTANCE_CRITERIA:
        _fail(
            "SCHEMA_INVALID",
            f"acceptance_criteria exceeds maximum item count {MAX_ACCEPTANCE_CRITERIA}",
        )

    normalized: list[str] = []
    total_bytes = 0
    for index, item in enumerate(value):
        if not isinstance(item, str):
            _fail("SCHEMA_INVALID", f"acceptance_criteria[{index}] must be a string")
        item = item.strip()
        if not item:
            _fail("SCHEMA_INVALID", f"acceptance_criteria[{index}] must be non-empty")
        if "\x00" in item:
            _fail("SCHEMA_INVALID", f"acceptance_criteria[{index}] must not contain NUL characters")
        item_bytes = len(item.encode("utf-8"))
        if item_bytes > MAX_ACCEPTANCE_CRITERION_LENGTH:
            _fail(
                "SCHEMA_INVALID",
                f"acceptance_criteria[{index}] exceeds {MAX_ACCEPTANCE_CRITERION_LENGTH} UTF-8 bytes",
            )
        total_bytes += item_bytes
        normalized.append(item)
    if total_bytes > MAX_ACCEPTANCE_CRITERIA_BYTES:
        _fail(
            "SCHEMA_INVALID",
            f"acceptance_criteria exceeds {MAX_ACCEPTANCE_CRITERIA_BYTES} UTF-8 bytes",
        )
    if len(set(normalized)) != len(normalized):
        _fail("SCHEMA_INVALID", "acceptance_criteria must not contain duplicates")
    return tuple(normalized)


def _bounded_integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("SCHEMA_INVALID", f"{name} must be an integer")
    if not minimum <= value <= maximum:
        _fail("SCHEMA_INVALID", f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class ExecutionClassificationInput:
    """Strict, non-persisted input descriptor for one classifier decision."""

    task_shape: str
    acceptance_criteria: Sequence[str]
    independent_review_required: bool
    artifact_size_bytes: int
    review_mode: str = ReviewMode.NONE.value
    parent_max_children: int | None = None

    def __post_init__(self) -> None:
        shape = _normalized_choice(
            "task_shape",
            self.task_shape,
            TaskShape,
            aliases={"SIMPLE": TaskShape.ATOMIC.value, "COMPOSITE": TaskShape.COMPLEX.value},
        )
        mode = _normalized_choice("review_mode", self.review_mode, ReviewMode)
        if not isinstance(self.independent_review_required, bool):
            _fail("SCHEMA_INVALID", "independent_review_required must be a boolean")
        criteria = _bounded_criteria(self.acceptance_criteria)
        artifact_size = _bounded_integer(
            self.artifact_size_bytes,
            "artifact_size_bytes",
            minimum=0,
            maximum=MAX_ARTIFACT_SIZE_BYTES,
        )
        parent_max = self.parent_max_children
        if parent_max is not None:
            parent_max = _bounded_integer(
                parent_max,
                "parent_max_children",
                minimum=0,
                maximum=MAX_PARENT_CHILDREN,
            )

        object.__setattr__(self, "task_shape", shape)
        object.__setattr__(self, "review_mode", mode)
        object.__setattr__(self, "acceptance_criteria", criteria)
        object.__setattr__(self, "artifact_size_bytes", artifact_size)
        object.__setattr__(self, "parent_max_children", parent_max)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionClassificationInput":
        """Build one strict descriptor without accepting transcript fields."""

        if not isinstance(payload, Mapping):
            _fail("SCHEMA_INVALID", "classifier input must be an object")
        candidate = dict(payload)
        aliases = {
            "mode": "review_mode",
            "artifact_size": "artifact_size_bytes",
            "max_children": "parent_max_children",
        }
        for alias, field_name in aliases.items():
            if alias not in candidate:
                continue
            if field_name in candidate and candidate[field_name] != candidate[alias]:
                _fail("SCHEMA_INVALID", f"conflicting aliases for {field_name}")
            candidate.setdefault(field_name, candidate.pop(alias))

        allowed = {
            "task_shape",
            "acceptance_criteria",
            "independent_review_required",
            "artifact_size_bytes",
            "review_mode",
            "parent_max_children",
        }
        unknown = sorted(set(candidate) - allowed)
        if unknown:
            _fail("SCHEMA_INVALID", "unsupported classifier fields: " + ", ".join(unknown))
        missing = sorted(
            {
                "task_shape",
                "acceptance_criteria",
                "independent_review_required",
                "artifact_size_bytes",
            }
            - set(candidate)
        )
        if missing:
            _fail("SCHEMA_INVALID", "missing classifier fields: " + ", ".join(missing))
        try:
            return cls(**candidate)
        except TypeError as exc:
            _fail("SCHEMA_INVALID", f"classifier input is incomplete: {exc}")
        raise AssertionError("_fail must raise")

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive, JSON-compatible descriptor representation."""

        return {
            "task_shape": self.task_shape,
            "acceptance_criteria": list(self.acceptance_criteria),
            "independent_review_required": self.independent_review_required,
            "artifact_size_bytes": self.artifact_size_bytes,
            "review_mode": self.review_mode,
            "parent_max_children": self.parent_max_children,
        }


# Descriptive alias for callers that use the shorter name.
ClassifierInput = ExecutionClassificationInput


def _coerce_input(
    request: ExecutionClassificationInput | Mapping[str, Any] | None,
    kwargs: Mapping[str, Any],
) -> ExecutionClassificationInput:
    if request is not None and kwargs:
        _fail("SCHEMA_INVALID", "pass classifier input or keyword fields, not both")
    if request is None:
        return ExecutionClassificationInput.from_mapping(kwargs)
    if isinstance(request, ExecutionClassificationInput):
        return request
    if isinstance(request, Mapping):
        return ExecutionClassificationInput.from_mapping(request)
    _fail("SCHEMA_INVALID", "classifier input must be an object")
    raise AssertionError("_fail must raise")


@dataclass(frozen=True, slots=True)
class ClassifierPolicy:
    """Deterministic policy with explicit, testable bounds."""

    atomic_artifact_limit_bytes: int = ATOMIC_ARTIFACT_LIMIT_BYTES
    complex_child_count: int = 2
    review_child_count: int = 1
    cross_review_child_count: int = 2

    def __post_init__(self) -> None:
        _bounded_integer(
            self.atomic_artifact_limit_bytes,
            "atomic_artifact_limit_bytes",
            minimum=0,
            maximum=MAX_ARTIFACT_SIZE_BYTES,
        )
        for name, value in (
            ("complex_child_count", self.complex_child_count),
            ("review_child_count", self.review_child_count),
            ("cross_review_child_count", self.cross_review_child_count),
        ):
            _bounded_integer(value, name, minimum=1, maximum=MAX_PROPOSED_CHILD_COUNT)

    def classify(
        self,
        request: ExecutionClassificationInput | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExecutionClassification:
        descriptor = _coerce_input(request, kwargs)
        classification = self._classify_kind(descriptor)
        if classification is ExecutionClass.ATOMIC:
            return ExecutionClassification(
                classification=classification.value,
                rationale=(
                    "Explicitly bounded atomic shape with one acceptance criterion, "
                    "no review requirement, and artifact size within the atomic limit."
                ),
                lenses=(),
                proposed_child_count=0,
                join_policy="NONE",
                unresolved_preconditions=(),
            )

        child_count, lenses, rationale = {
            ExecutionClass.COMPLEX: (
                self.complex_child_count,
                DEFAULT_COMPLEX_LENSES,
                "Task shape or bounded task inputs exceed the atomic boundary; use a bounded complex plan.",
            ),
            ExecutionClass.REVIEW: (
                self.review_child_count,
                DEFAULT_REVIEW_LENSES,
                "Declared review intent requires a bounded review plan before parent acceptance.",
            ),
            ExecutionClass.CROSS_REVIEW: (
                self.cross_review_child_count,
                DEFAULT_CROSS_REVIEW_LENSES,
                "Independent review intent requires bounded independent review contexts.",
            ),
        }[classification]
        if (
            descriptor.parent_max_children is not None
            and child_count > descriptor.parent_max_children
        ):
            _fail(
                "REPLAN_REQUIRED",
                "classifier proposal exceeds parent_max_children; refusing silent truncation or scope expansion",
            )
        return ExecutionClassification(
            classification=classification.value,
            rationale=rationale,
            lenses=lenses,
            proposed_child_count=child_count,
            join_policy="ALL_REQUIRED",
            unresolved_preconditions=(),
        )

    def _classify_kind(self, descriptor: ExecutionClassificationInput) -> ExecutionClass:
        """Apply strongest explicit review signal before complexity signals."""

        if (
            descriptor.independent_review_required
            or descriptor.review_mode == ReviewMode.CROSS_REVIEW.value
            or descriptor.task_shape == TaskShape.CROSS_REVIEW.value
        ):
            return ExecutionClass.CROSS_REVIEW
        if (
            descriptor.review_mode == ReviewMode.REVIEW.value
            or descriptor.task_shape == TaskShape.REVIEW.value
        ):
            return ExecutionClass.REVIEW
        if (
            descriptor.task_shape == TaskShape.COMPLEX.value
            or len(descriptor.acceptance_criteria) > 1
            or descriptor.artifact_size_bytes > self.atomic_artifact_limit_bytes
        ):
            return ExecutionClass.COMPLEX
        return ExecutionClass.ATOMIC


def classify_execution(
    request: ExecutionClassificationInput | Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> ExecutionClassification:
    """Classify one explicit bounded descriptor with the default policy."""

    return ClassifierPolicy().classify(request, **kwargs)


# Compatibility/readability alias for callers that use task-oriented wording.
classify_task = classify_execution


__all__ = [
    "CLASSIFIER_POLICY_SCHEMA_VERSION",
    "ATOMIC_ARTIFACT_LIMIT_BYTES",
    "MAX_ARTIFACT_SIZE_BYTES",
    "MAX_ACCEPTANCE_CRITERIA",
    "MAX_ACCEPTANCE_CRITERION_LENGTH",
    "MAX_ACCEPTANCE_CRITERIA_BYTES",
    "MAX_PARENT_CHILDREN",
    "DEFAULT_COMPLEX_LENSES",
    "DEFAULT_REVIEW_LENSES",
    "DEFAULT_CROSS_REVIEW_LENSES",
    "TaskShape",
    "ReviewMode",
    "ClassifierPolicyError",
    "ExecutionClassificationInput",
    "ClassifierInput",
    "ClassifierPolicy",
    "classify_execution",
    "classify_task",
]
