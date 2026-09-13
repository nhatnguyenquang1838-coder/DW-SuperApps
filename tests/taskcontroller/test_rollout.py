"""TC-MBX-905: capability-gated staged mailbox rollout.

The rollout policy is intentionally decision-only.  These tests prove that
choosing a protocol does not rewrite the v1 request, mailbox shape, or run
schema, and that required v2 lanes fail closed instead of silently downgrading.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from taskcontroller.controlplane.rollout import (
    DEFAULT_V2_CAPABILITY,
    RolloutConfig,
    RolloutDisposition,
    RolloutMode,
    decide_rollout,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V1_PROTOCOL, V2_PROTOCOL


_REQUEST = {
    "protocol": "dw.taskcontroller.a2a/v1",
    "run_id": "run-905",
    "node_id": "node-905",
    "seq": 7,
    "payload": {
        "objective": "Keep the legacy request unchanged.",
        "scope": {"allowed_actions": ["read_repo"]},
    },
}


def _agent(*capabilities: str) -> dict[str, object]:
    return {
        "provider_id": "agent-905",
        "capability_refs": [
            {"capability_id": capability} for capability in capabilities
        ],
    }


def _config(
    mode: RolloutMode = RolloutMode.V2_PREFERRED,
    *,
    feature_flag: bool = False,
) -> RolloutConfig:
    return RolloutConfig(mode=mode, feature_flag=feature_flag)


class TestStagedEnablement:
    def test_agent_instance_capability_selects_v2(self) -> None:
        request = deepcopy(_REQUEST)

        decision = decide_rollout(
            _agent(DEFAULT_V2_CAPABILITY),
            request,
            config=_config(),
            v2_available=True,
            request_v2_supported=True,
        )

        assert decision.disposition is RolloutDisposition.V2_SELECTED
        assert decision.protocol == V2_PROTOCOL
        assert decision.code == "V2_SELECTED"
        assert decision.v2_enabled is True
        assert decision.request is request
        assert request == _REQUEST

    def test_project_runtime_feature_flag_selects_v2_without_agent_capability(self) -> None:
        request = deepcopy(_REQUEST)

        decision = decide_rollout(
            _agent(),
            request,
            config=_config(feature_flag=True),
            v2_available=True,
            request_v2_supported=True,
        )

        assert decision.disposition is RolloutDisposition.V2_SELECTED
        assert decision.protocol == V2_PROTOCOL
        assert decision.capability_enabled is False
        assert decision.feature_flag_enabled is True

    def test_absent_explicit_enablement_stays_on_v1(self) -> None:
        request = deepcopy(_REQUEST)

        decision = decide_rollout(
            _agent(), request, config=_config(), v2_available=True
        )

        assert decision.disposition is RolloutDisposition.V1_FALLBACK
        assert decision.protocol == V1_PROTOCOL
        assert decision.code == "V2_NOT_ENABLED"
        assert decision.request is request

    def test_v1_only_is_an_immediate_rollback_even_when_v2_is_advertised(self) -> None:
        request = deepcopy(_REQUEST)

        decision = decide_rollout(
            _agent(DEFAULT_V2_CAPABILITY),
            request,
            config=_config(RolloutMode.V1_ONLY, feature_flag=True),
            v2_available=True,
            request_v2_supported=True,
        )

        assert decision.disposition is RolloutDisposition.V1_FALLBACK
        assert decision.protocol == V1_PROTOCOL
        assert decision.code == "V2_DISABLED"
        assert decision.request is request


class TestFallbackAndFailClosed:
    def test_preferred_mode_falls_back_when_v2_is_unavailable(self) -> None:
        request = deepcopy(_REQUEST)
        before = deepcopy(request)

        decision = decide_rollout(
            _agent(DEFAULT_V2_CAPABILITY),
            request,
            config=_config(),
            v2_available=False,
            request_v2_supported=True,
        )

        assert decision.disposition is RolloutDisposition.V1_FALLBACK
        assert decision.protocol == V1_PROTOCOL
        assert decision.code == "V2_UNAVAILABLE"
        assert decision.request is request
        assert request == before

    def test_preferred_mode_falls_back_when_request_is_not_v2_safe(self) -> None:
        request = deepcopy(_REQUEST)
        before = deepcopy(request)

        decision = decide_rollout(
            _agent(DEFAULT_V2_CAPABILITY),
            request,
            config=_config(),
            v2_available=True,
            request_v2_supported=False,
        )

        assert decision.disposition is RolloutDisposition.V1_FALLBACK
        assert decision.protocol == V1_PROTOCOL
        assert decision.code == "V2_REQUEST_UNSUPPORTED"
        assert decision.request is request
        assert request == before

    @pytest.mark.parametrize(
        "available,supported,code",
        [
            (False, True, "V2_UNAVAILABLE"),
            (True, False, "V2_REQUEST_UNSUPPORTED"),
        ],
    )
    def test_required_mode_blocks_without_silent_downgrade(
        self, available: bool, supported: bool, code: str
    ) -> None:
        request = deepcopy(_REQUEST)
        before = deepcopy(request)

        decision = decide_rollout(
            _agent(DEFAULT_V2_CAPABILITY),
            request,
            config=_config(RolloutMode.V2_REQUIRED),
            v2_available=available,
            request_v2_supported=supported,
        )

        assert decision.disposition is RolloutDisposition.BLOCKED
        assert decision.protocol is None
        assert decision.code == code
        assert decision.request is request
        assert request == before

    def test_required_mode_without_explicit_enablement_blocks(self) -> None:
        request = deepcopy(_REQUEST)

        decision = decide_rollout(
            _agent(),
            request,
            config=_config(RolloutMode.V2_REQUIRED),
            v2_available=True,
            request_v2_supported=True,
        )

        assert decision.disposition is RolloutDisposition.BLOCKED
        assert decision.protocol is None
        assert decision.code == "V2_NOT_ENABLED"
        assert decision.request is request


class TestPolicyBoundaries:
    def test_malformed_control_inputs_fail_closed(self) -> None:
        with pytest.raises(TaskControllerValidationError, match="feature_flag"):
            RolloutConfig(feature_flag=1)  # type: ignore[arg-type]

        with pytest.raises(TaskControllerValidationError, match="capability_refs"):
            decide_rollout(
                {"provider_id": "agent-905", "capability_refs": "mailbox.v2"},
                deepcopy(_REQUEST),
                config=_config(feature_flag=True),
            )

    def test_policy_has_no_dispatch_or_transport_side_effect_surface(self) -> None:
        from taskcontroller.controlplane import rollout

        source = Path(rollout.__file__).read_text(encoding="utf-8")
        assert "subprocess" not in source
        assert "requests" not in source
        assert "github" not in source.lower()
        assert "slack" not in source.lower()
        assert "socket" not in source.lower()

    def test_decision_does_not_rewrite_a_v1_request_or_add_v2_schema_fields(self) -> None:
        request = deepcopy(_REQUEST)
        before = deepcopy(request)

        decision = decide_rollout(
            _agent(DEFAULT_V2_CAPABILITY),
            request,
            config=_config(),
            v2_available=True,
            request_v2_supported=True,
        )

        assert request == before
        assert decision.request is request
        assert set(request) == {"protocol", "run_id", "node_id", "seq", "payload"}
