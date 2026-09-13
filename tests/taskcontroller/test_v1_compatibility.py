from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope
from taskcontroller.interaction.mailbox_v2 import canonical_digest


FIXTURES = Path(__file__).with_name("fixtures")


def _v1_command() -> dict[str, Any]:
    payload = json.loads((FIXTURES / "v1_contract_fixtures.json").read_text(encoding="utf-8"))
    command = copy.deepcopy(payload["cases"]["missing_identity"])
    command["run_id"] = "run-1"
    command["node_id"] = "node-1"
    command["sender"] = "controller-1"
    command["recipient"] = "hermes-mac"
    command["seq"] = 1
    command["request"] = "Run one bounded mailbox v2 contract check."
    return command


def _bound_v2(legacy: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads((FIXTURES / "v2_contract_fixtures.json").read_text(encoding="utf-8"))
    candidate = copy.deepcopy(payload["cases"]["execution_request"])
    candidate["run_id"] = legacy["run_id"]
    candidate["node_id"] = legacy["node_id"]
    candidate["seq"] = legacy["seq"]
    candidate["producer"]["actor_id"] = legacy["sender"]
    candidate["recipient"]["agent_instance"] = legacy["recipient"]
    candidate["logical_contract"]["objective"] = legacy["request"]
    candidate["payload"]["objective"] = legacy["request"]
    candidate["execution_identity"]["run_id"] = legacy["run_id"]
    candidate["execution_identity"]["node_id"] = legacy["node_id"]
    candidate["digest"] = canonical_digest(candidate)
    return candidate


def _adapter():
    try:
        from taskcontroller.interaction.compatibility import (
            V1CompatibilityAdapter,
            adapt_v1_request_to_v2,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"v1 compatibility adapter is missing: {exc}")
    return V1CompatibilityAdapter, adapt_v1_request_to_v2


def test_supported_v1_command_is_losslessly_bound_to_explicit_v2_fields() -> None:
    _, adapt = _adapter()
    legacy = _v1_command()
    bound = _bound_v2(legacy)
    original = copy.deepcopy(legacy)

    adapted = adapt(legacy, bound_v2_fields=bound)

    assert adapted.protocol == "dw.taskcontroller.mailbox/v2"
    assert adapted.run_id == legacy["run_id"]
    assert adapted.node_id == legacy["node_id"]
    assert adapted.seq == legacy["seq"]
    assert adapted.to_dict()["payload"]["legacy_v1"] == legacy
    assert adapted.to_dict()["payload"]["objective"] == legacy["request"]
    assert adapted.to_dict()["digest"] == adapted.digest()
    assert legacy == original


def test_adapter_accepts_the_existing_immutable_v1_envelope_object() -> None:
    Adapter, _ = _adapter()
    legacy = _v1_command()
    envelope = A2AEnvelope.from_dict(legacy)

    adapted = Adapter.to_v2(envelope, bound_v2_fields=_bound_v2(legacy))

    assert adapted.to_dict()["payload"]["legacy_v1"] == legacy


def test_adapter_never_infers_missing_v2_bindings() -> None:
    _, adapt = _adapter()
    legacy = _v1_command()
    bound = _bound_v2(legacy)
    bound.pop("execution_identity")

    with pytest.raises(TaskControllerValidationError) as exc_info:
        adapt(legacy, bound_v2_fields=bound)

    assert getattr(exc_info.value, "code", None) == "PROTOCOL_DOWNGRADE_UNSUPPORTED"


def test_adapter_rejects_v1_result_or_review_as_an_execution_request() -> None:
    _, adapt = _adapter()
    legacy = _v1_command()
    legacy["kind"] = "REPORT"

    with pytest.raises(TaskControllerValidationError) as exc_info:
        adapt(legacy, bound_v2_fields=_bound_v2(_v1_command()))

    assert getattr(exc_info.value, "code", None) == "PROTOCOL_DOWNGRADE_UNSUPPORTED"


def test_adapter_rejects_v2_only_semantics_embedded_in_v1_state() -> None:
    _, adapt = _adapter()
    legacy = _v1_command()
    legacy["state"]["execution_identity"] = {"lease_generation": 9}

    with pytest.raises(TaskControllerValidationError) as exc_info:
        adapt(legacy, bound_v2_fields=_bound_v2(_v1_command()))

    assert getattr(exc_info.value, "code", None) == "REPLAN_REQUIRED"


def test_adapter_rejects_identity_or_objective_mismatch_in_explicit_binding() -> None:
    _, adapt = _adapter()
    legacy = _v1_command()
    bound = _bound_v2(legacy)
    bound["node_id"] = "other-node"
    bound["digest"] = canonical_digest(bound)

    with pytest.raises(TaskControllerValidationError) as exc_info:
        adapt(legacy, bound_v2_fields=bound)

    assert getattr(exc_info.value, "code", None) == "CONTRACT_MISMATCH"


def test_legacy_fixture_round_trip_remains_v1_only_and_unmodified() -> None:
    payload = json.loads((FIXTURES / "v1_contract_fixtures.json").read_text(encoding="utf-8"))
    for case in ("executor_progress", "terminal_result"):
        candidate = payload["cases"][case]
        envelope_payload = candidate["envelope"] if "envelope" in candidate else candidate
        envelope = A2AEnvelope.from_dict(envelope_payload)
        assert envelope.to_dict() == envelope_payload
        assert envelope.to_dict()["protocol"] == "dw.taskcontroller.a2a/v1"
