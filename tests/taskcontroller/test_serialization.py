"""WP0 JSON round-trip (to_dict -> from_dict -> equality) tests for all 12 models."""

from __future__ import annotations

import pytest

MODEL_FIXTURES = [
    "host_profile", "capability_card", "provider_card", "task_contract",
    "exec_request", "exec_receipt", "agent_event", "artifact",
    "review_result", "work_lease", "team_run_state", "controller_decision",
]


@pytest.mark.parametrize("fixture_name", MODEL_FIXTURES)
def test_round_trip(fixture_name, request):
    obj = request.getfixturevalue(fixture_name)
    d = obj.to_dict()
    restored = obj.__class__.from_dict(d)
    assert restored.to_dict() == d


@pytest.mark.parametrize("fixture_name", MODEL_FIXTURES)
def test_round_trip_via_serialization(fixture_name, request):
    import taskcontroller
    obj = request.getfixturevalue(fixture_name)
    d = taskcontroller.to_dict(obj)
    name = {
        "host_profile": "controller_host_profile",
        "capability_card": "capability_card",
        "provider_card": "execution_provider_card",
        "task_contract": "task_contract",
        "exec_request": "execution_request",
        "exec_receipt": "execution_receipt",
        "agent_event": "agent_event",
        "artifact": "artifact",
        "review_result": "review_result",
        "work_lease": "work_lease",
        "team_run_state": "team_run_state",
        "controller_decision": "controller_decision",
    }[fixture_name]
    restored = taskcontroller.from_dict(name, d)
    assert taskcontroller.to_dict(restored) == d
