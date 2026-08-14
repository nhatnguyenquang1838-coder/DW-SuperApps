"""WP6 S3 focused tests: interaction mapping / authority boundary (NO GWC)."""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.errors import ControlPlaneError
from taskcontroller.projections.actions import (
    ActionMapping,
    AuthorityResult,
    map_action,
)
from taskcontroller.controlplane.intents import ControlIntent


class TestControlActionMapping:
    def test_pause_maps_to_control_intent(self):
        m = map_action("PAUSE", "run.1", expected_version=7, command_id="cmd.1")
        assert isinstance(m.control_intent, ControlIntent)
        assert m.control_intent.intent == "PAUSE"
        assert m.control_intent.expected_version == 7
        assert m.control_intent.command_id == "cmd.1"
        assert m.authority_result is None

    def test_resume_cancel_map(self):
        for act in ("RESUME", "CANCEL"):
            m = map_action(act, "run.1", expected_version=3)
            assert m.control_intent.intent == act
            assert m.control_intent.expected_version == 3

    def test_replan_requires_new_plan_version(self):
        with pytest.raises(ValueError):
            map_action("REPLAN", "run.1", expected_version=3)
        m = map_action("REPLAN", "run.1", expected_version=3, new_plan_version="p2")
        assert m.control_intent.new_plan_version == "p2"

    def test_stale_version_passes_through_to_cas(self):
        # the mapper never touches/validates expected_version; WP5 CAS rejects it
        m = map_action("PAUSE", "run.1", expected_version=999, command_id="c")
        assert m.control_intent.expected_version == 999  # untouched


class TestAuthorityBoundary:
    def test_approve_is_authority_only_no_runtime(self):
        m = map_action("APPROVE", "run.1", expected_version=5)
        assert m.control_intent is None
        assert isinstance(m.authority_result, AuthorityResult)
        assert m.authority_result.authority_required is True

    def test_merge_is_authority_only(self):
        m = map_action("MERGE", "run.1", expected_version=5)
        assert m.authority_result is not None
        assert m.control_intent is None

    def test_unknown_action_fails_closed(self):
        with pytest.raises(ValueError):
            map_action("FORCE_DONE", "run.1", expected_version=5)
