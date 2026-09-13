"""TC-MBX-502: deterministic execution-classifier policy tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.classifier import (
    ATOMIC_ARTIFACT_LIMIT_BYTES,
    ClassifierPolicyError,
    ExecutionClassificationInput,
    classify_execution,
)
from taskcontroller.execution.classification import ExecutionClass


_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "taskcontroller"
        / "schemas"
        / "execution_classification.schema.json"
    ).read_text(encoding="utf-8")
)
_SCHEMA_VALIDATOR = Draft202012Validator(_SCHEMA)


def _classify(**changes: object):
    values: dict[str, object] = {
        "task_shape": "ATOMIC",
        "acceptance_criteria": ("one bounded acceptance criterion",),
        "independent_review_required": False,
        "artifact_size_bytes": ATOMIC_ARTIFACT_LIMIT_BYTES,
        "review_mode": "NONE",
    }
    values.update(changes)
    return classify_execution(**values)


def test_atomic_boundary_is_inclusive_and_over_limit_becomes_complex() -> None:
    at_limit = _classify(artifact_size_bytes=ATOMIC_ARTIFACT_LIMIT_BYTES)
    over_limit = _classify(artifact_size_bytes=ATOMIC_ARTIFACT_LIMIT_BYTES + 1)

    assert at_limit.classification == ExecutionClass.ATOMIC.value
    assert at_limit.proposed_child_count == 0
    assert at_limit.join_policy == "NONE"
    assert over_limit.classification == ExecutionClass.COMPLEX.value
    assert over_limit.proposed_child_count > 0
    assert over_limit.join_policy == "ALL_REQUIRED"


def test_review_intent_precedes_atomic_shape_and_independent_review_is_cross_review() -> None:
    ordinary_review = _classify(review_mode="REVIEW")
    cross_review_mode = _classify(review_mode="CROSS_REVIEW")
    cross_review_requirement = _classify(independent_review_required=True)

    assert ordinary_review.classification == ExecutionClass.REVIEW.value
    assert ordinary_review.proposed_child_count > 0
    assert cross_review_mode.classification == ExecutionClass.CROSS_REVIEW.value
    assert cross_review_requirement.classification == ExecutionClass.CROSS_REVIEW.value


def test_shape_and_acceptance_criteria_prevent_false_atomic_classification() -> None:
    complex_shape = _classify(task_shape="COMPLEX")
    review_shape = _classify(task_shape="REVIEW")
    multiple_criteria = _classify(
        acceptance_criteria=("first", "second"),
    )

    assert complex_shape.classification == ExecutionClass.COMPLEX.value
    assert review_shape.classification == ExecutionClass.REVIEW.value
    assert multiple_criteria.classification == ExecutionClass.COMPLEX.value


def test_parent_child_budget_is_never_exceeded_or_silently_truncated() -> None:
    with pytest.raises(ClassifierPolicyError) as error:
        _classify(task_shape="COMPLEX", parent_max_children=1)

    assert error.value.code == "REPLAN_REQUIRED"
    assert "parent_max_children" in str(error.value)

    bounded = _classify(task_shape="COMPLEX", parent_max_children=2)
    assert bounded.proposed_child_count <= 2


def test_policy_input_is_bounded_and_rejects_prompt_or_transcript_fields() -> None:
    with pytest.raises(TaskControllerValidationError, match="unsupported classifier fields"):
        _classify(prompt="must never enter the classifier")

    with pytest.raises(TaskControllerValidationError, match="independent_review_required"):
        _classify(independent_review_required="yes")

    with pytest.raises(TaskControllerValidationError, match="artifact_size_bytes"):
        _classify(artifact_size_bytes=-1)

    with pytest.raises(TaskControllerValidationError, match="acceptance_criteria"):
        _classify(acceptance_criteria=())


def test_mapping_aliases_and_input_normalization_are_deterministic() -> None:
    canonical = ExecutionClassificationInput.from_mapping(
        {
            "task_shape": "atomic",
            "acceptance_criteria": ["one bounded acceptance criterion"],
            "independent_review_required": False,
            "artifact_size": ATOMIC_ARTIFACT_LIMIT_BYTES,
            "mode": "none",
        }
    )
    first = classify_execution(canonical)
    second = classify_execution(
        task_shape="ATOMIC",
        acceptance_criteria=("one bounded acceptance criterion",),
        independent_review_required=False,
        artifact_size_bytes=ATOMIC_ARTIFACT_LIMIT_BYTES,
        review_mode="NONE",
    )

    assert first.to_dict() == second.to_dict()
    assert first.digest() == second.digest()


def test_policy_output_is_exactly_tc501_schema_metadata() -> None:
    for value in (
        _classify(),
        _classify(review_mode="REVIEW"),
        _classify(independent_review_required=True),
        _classify(task_shape="COMPLEX"),
    ):
        payload = value.to_dict()
        assert set(payload) == {
            "classification",
            "rationale",
            "lenses",
            "proposed_child_count",
            "join_policy",
            "unresolved_preconditions",
        }
        _SCHEMA_VALIDATOR.validate(payload)
        assert "reasoning_trace" not in payload
        assert "prompt" not in payload
