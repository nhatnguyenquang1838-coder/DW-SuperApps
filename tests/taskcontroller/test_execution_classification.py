"""TC-MBX-501: bounded normalized execution-classification metadata."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.classification import (
    CLASSIFICATION_SCHEMA_VERSION,
    MAX_LENSES,
    MAX_PRECONDITIONS,
    MAX_PROPOSED_CHILD_COUNT,
    MAX_RATIONALE_LENGTH,
    ExecutionClassification,
    ExecutionClass,
)


_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "taskcontroller"
        / "schemas"
        / "execution_classification.schema.json"
    ).read_text(encoding="utf-8")
)
_SCHEMA_VALIDATOR = Draft202012Validator(_SCHEMA)


def _validate_schema(payload: dict[str, object]) -> None:
    _SCHEMA_VALIDATOR.validate(payload)


def _classification(kind: str = "COMPLEX", **changes: object) -> ExecutionClassification:
    values: dict[str, object] = {
        "classification": kind,
        "rationale": "The task has bounded independent work that is useful to plan explicitly.",
        "lenses": ("architecture", "implementation"),
        "proposed_child_count": 2,
        "join_policy": "ALL_REQUIRED",
        "unresolved_preconditions": ("source_digest_verified",),
    }
    if kind == "ATOMIC":
        values.update(
            lenses=(),
            proposed_child_count=0,
            join_policy="NONE",
            unresolved_preconditions=(),
        )
    values.update(changes)
    return ExecutionClassification(**values)


def test_all_classification_values_round_trip_as_schema_valid_metadata() -> None:
    for kind in ("ATOMIC", "COMPLEX", "REVIEW", "CROSS_REVIEW"):
        value = _classification(kind)
        payload = value.to_dict()

        assert value.classification == ExecutionClass(kind).value
        assert CLASSIFICATION_SCHEMA_VERSION.endswith("/v1")
        assert set(payload) == {
            "classification",
            "rationale",
            "lenses",
            "proposed_child_count",
            "join_policy",
            "unresolved_preconditions",
        }
        _validate_schema(payload)
        assert ExecutionClassification.from_dict(payload) == value


def test_normalized_metadata_has_stable_order_bytes_and_digest() -> None:
    first = _classification(
        lenses=("implementation", "architecture"),
        unresolved_preconditions=("zulu", "alpha"),
    )
    second = _classification(
        lenses=("architecture", "implementation"),
        unresolved_preconditions=("alpha", "zulu"),
    )

    assert first.to_dict() == second.to_dict()
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.digest() == second.digest()
    assert first.digest().startswith("sha256:")


def test_metadata_is_defensive_and_has_no_transcript_slot() -> None:
    value = _classification()
    payload = value.to_dict()
    payload["lenses"].append("mutated")
    payload["unresolved_preconditions"].append("mutated")

    assert "mutated" not in value.to_dict()["lenses"]
    assert "mutated" not in value.to_dict()["unresolved_preconditions"]

    transcript_payload = copy.deepcopy(value.to_dict())
    transcript_payload["reasoning_transcript"] = "hidden chain of thought"
    with pytest.raises(TaskControllerValidationError, match="unsupported fields"):
        ExecutionClassification.from_dict(transcript_payload)


def test_schema_rejects_transcript_and_inconsistent_shape() -> None:
    transcript_payload = _classification().to_dict()
    transcript_payload["reasoning_trace"] = "hidden chain of thought"
    with pytest.raises(ValidationError):
        _validate_schema(transcript_payload)

    inconsistent_payload = _classification("ATOMIC").to_dict()
    inconsistent_payload["proposed_child_count"] = 1
    with pytest.raises(ValidationError):
        _validate_schema(inconsistent_payload)


def test_bounds_reject_unbounded_classification_metadata() -> None:
    with pytest.raises(TaskControllerValidationError, match="rationale"):
        _classification(rationale="x" * (MAX_RATIONALE_LENGTH + 1))

    with pytest.raises(TaskControllerValidationError, match="lenses"):
        _classification(lenses=tuple(f"lens-{i}" for i in range(MAX_LENSES + 1)))

    with pytest.raises(TaskControllerValidationError, match="unresolved_preconditions"):
        _classification(
            unresolved_preconditions=tuple(
                f"precondition-{i}" for i in range(MAX_PRECONDITIONS + 1)
            )
        )

    with pytest.raises(TaskControllerValidationError, match="proposed_child_count"):
        _classification(proposed_child_count=MAX_PROPOSED_CHILD_COUNT + 1)


def test_classification_shape_is_fail_closed() -> None:
    with pytest.raises(TaskControllerValidationError, match="ATOMIC"):
        _classification("ATOMIC", proposed_child_count=1, join_policy="ALL_REQUIRED")

    with pytest.raises(TaskControllerValidationError, match="non-ATOMIC"):
        _classification("REVIEW", proposed_child_count=0, join_policy="NONE")

    with pytest.raises(TaskControllerValidationError, match="lens"):
        _classification("CROSS_REVIEW", lenses=())


def test_from_dict_rejects_missing_and_unknown_fields() -> None:
    payload = _classification().to_dict()
    payload.pop("rationale")
    with pytest.raises(TaskControllerValidationError, match="missing fields"):
        ExecutionClassification.from_dict(payload)

    payload = _classification().to_dict()
    payload["prompt"] = "raw task prompt"
    with pytest.raises(TaskControllerValidationError, match="unsupported fields"):
        ExecutionClassification.from_dict(payload)
