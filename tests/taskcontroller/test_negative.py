"""WP0 negative-case tests: invalid ids/versions/dep-refs, stale/late, etc."""

from __future__ import annotations

import pytest

import taskcontroller
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.domain.enums import ActorKind, TrustTier
from taskcontroller.domain.ids import TaskRef
from taskcontroller.domain.models import TaskContract
from taskcontroller.domain.values import ScopeSpec, CapabilityRequirement, EnvironmentInfo, Binding


def _tc(cap_req, **over):
    kw = dict(
        contract_id="tc.1", run_id="run.1", node_id="node.a",
        objective="x", scope=ScopeSpec(), acceptance_criteria=["ok"],
        capability_requirement=cap_req, dependencies=[],
    )
    kw.update(over)
    return TaskContract(**kw)


def test_invalid_id_pattern(cap_req):
    with pytest.raises(TaskControllerValidationError):
        _tc(cap_req, contract_id="bad id!")  # space + bang


def test_invalid_dependency_ref(cap_req):
    with pytest.raises(TaskControllerValidationError):
        _tc(cap_req, dependencies=[TaskRef(run_id="run/1", node_id="node.a")])


def test_attempt_less_than_one_fails_schema(exec_request):
    d = taskcontroller.to_dict(exec_request)
    d["attempt"] = 0
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("execution_request", d)


def test_empty_fencing_token_fails_schema(exec_request):
    d = taskcontroller.to_dict(exec_request)
    d["fencing_token"] = ""
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("execution_request", d)


def test_missing_required_field_fails_schema(exec_receipt):
    d = taskcontroller.to_dict(exec_receipt)
    d["execution_ref"].pop("fencing_token")  # drop a required nested field
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("execution_receipt", d)


def test_actor_kind_enum_is_role_not_provider(host_profile):
    # HostType renamed to ActorKind; must reject provider-kind values here
    d = host_profile.to_dict()
    d["actor_kind"] = "LOCAL"  # provider kind, not an actor role
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.from_dict("controller_host_profile", d)
    # and schema rejects it too
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("controller_host_profile", d)


def test_provider_card_supports_local_without_bindings(cap_req):
    from taskcontroller.domain.models import ExecutionProviderCard
    from taskcontroller.domain.enums import ProviderKind

    card = ExecutionProviderCard(
        provider_id="prov.local.py", provider_kind=ProviderKind.LOCAL.value,
        capability_refs=[], bindings=[],  # local provider may have no binding
    )
    d = taskcontroller.to_dict(card)
    taskcontroller.validate("execution_provider_card", d)


def test_unknown_binding_type_rejected():
    with pytest.raises(TaskControllerValidationError):
        Binding(kind="SLACK", endpoint_ref="x")  # not a generic BindingType


def test_review_verdict_invalid_fails_schema(review_result):
    d = taskcontroller.to_dict(review_result)
    d["verdict"] = "MAYBE"
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("review_result", d)


def test_decision_type_invalid_fails_schema(controller_decision):
    d = taskcontroller.to_dict(controller_decision)
    d["decision_type"] = "DEFER"
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.validate("controller_decision", d)


def test_host_profile_env_requires_host_fields():
    # environment is required
    with pytest.raises(TaskControllerValidationError):
        taskcontroller.from_dict("controller_host_profile", {
            "host_id": "h1", "actor_kind": ActorKind.AGENT.value,
            "trust_tier": TrustTier.STANDARD.value, "bindings": [],
            "capabilities": [], "version": "1",
        })
