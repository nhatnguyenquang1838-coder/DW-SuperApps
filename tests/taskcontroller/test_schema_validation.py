"""WP0 JSON Schema validation tests (each model validates vs its schema)."""

from __future__ import annotations

import pytest

import taskcontroller
from taskcontroller.errors import TaskControllerValidationError

MODEL_NAME_FIXTURE = {
    "controller_host_profile": "host_profile",
    "capability_card": "capability_card",
    "execution_provider_card": "provider_card",
    "task_contract": "task_contract",
    "execution_request": "exec_request",
    "execution_receipt": "exec_receipt",
    "agent_event": "agent_event",
    "artifact": "artifact",
    "review_result": "review_result",
    "work_lease": "work_lease",
    "team_run_state": "team_run_state",
    "controller_decision": "controller_decision",
}


@pytest.mark.parametrize("model_name", list(MODEL_NAME_FIXTURE.keys()))
def test_valid_instance_passes_schema(model_name, request):
    fixture_name = MODEL_NAME_FIXTURE[model_name]
    obj = request.getfixturevalue(fixture_name)
    d = taskcontroller.to_dict(obj)
    taskcontroller.validate(model_name, d)  # must not raise


def test_all_12_schemas_present():
    names = taskcontroller.model_names()
    assert len(names) == 12
    assert set(names) == set(MODEL_NAME_FIXTURE.keys())


def test_invalid_status_enum_fails_schema(exec_receipt):
    d = taskcontroller.to_dict(exec_receipt)
    d["status"] = "NONSENSE"
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("execution_receipt", d)
