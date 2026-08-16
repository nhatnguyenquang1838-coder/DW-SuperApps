"""WP3 (#50) focused tests — MVP public human action fidelity.

Proves: exact/contextual public action set; STOP is first-class and is NOT
CANCEL structurally or semantically; STOP blocks the next work-unit start at a
safe boundary; evidence/state preserved with no fabricated DONE; stale/invalid
requests fail closed; APPROVE/MERGE are authority-only with zero mutation;
internal RESUME/CANCEL/REPLAN never surface in the default RootCard API;
unknown actions fail closed; and no deferred Full-E2E core is activated.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp import actions as ma
from taskcontroller.mvp.actions import (
    APPROVE,
    AUTHORITY_ACTIONS,
    CONTROL_ACTIONS,
    FORBIDDEN_DISPOSITIONS,
    INTERNAL_RUNTIME_VERBS,
    MERGE,
    PAUSE,
    PUBLIC_ACTIONS,
    STOP,
    Disposition,
    MvpControlState,
    PublicActionRequest,
    PublicActionResult,
    SafeBoundary,
    SafeBoundaryUnavailableError,
    StaleControlRequestError,
    WorkUnitBlockedError,
    apply_public_action,
    contextual_actions,
    default_safe_boundary,
    start_work_unit,
)
from taskcontroller.mvp.rootcard import (
    NON_PUBLIC_ACTIONS,
    PUBLIC_ROOTCARD_ACTIONS,
    PlanBlock,
    RootCard,
    render_rootcard,
)
from taskcontroller.mvp.protocol_bridge import CONTINUE, ContractedSubtask

ACTIONS_SOURCE = Path(ma.__file__)


def _state(**overrides) -> MvpControlState:
    base = dict(
        run_id="RUN-47",
        disposition=Disposition.RUNNING,
        current_work_unit="S2",
        evidence=("WP1 gate validated", "WP2 rootcard green"),
        revision=3,
    )
    base.update(overrides)
    return MvpControlState(**base)


def _contract(subtask_id: str) -> ContractedSubtask:
    return ContractedSubtask(
        subtask_id=subtask_id,
        objective=f"objective for {subtask_id}",
        allowed_work=("bounded work",),
        expected_output=("artifact",),
        report_requirement=("evidence",),
        after_report=CONTINUE,
    )


def _rootcard(**overrides) -> RootCard:
    base = dict(
        run_id="RUN-47",
        human_owner="Nhat",
        controller="ChatGPT",
        executor="Hermes Cloud",
        plan=PlanBlock.from_contracts(tuple(_contract(f"S{i}") for i in (1, 2, 3))),
        active_subtask_id="S2",
        now="WP3 in_progress",
        next="controller readback",
        last_material_update="WP2 validated",
    )
    base.update(overrides)
    return RootCard(**base)


# ---------------------------------------------------------------- 1
class TestExactPublicActionSet:
    """WP3-1: the public API is exactly PAUSE|STOP|APPROVE|MERGE, contextual."""

    def test_public_action_set_is_exact_and_ordered(self):
        assert PUBLIC_ACTIONS == ("PAUSE", "STOP", "APPROVE", "MERGE")
        assert len(set(PUBLIC_ACTIONS)) == 4
        assert CONTROL_ACTIONS == (PAUSE, STOP)
        assert AUTHORITY_ACTIONS == (APPROVE, MERGE)

    def test_rootcard_consumes_the_same_vocabulary(self):
        assert PUBLIC_ROOTCARD_ACTIONS is PUBLIC_ACTIONS
        assert NON_PUBLIC_ACTIONS is INTERNAL_RUNTIME_VERBS

    def test_contextual_defaults_are_pause_and_stop(self):
        assert contextual_actions(_state()) == (PAUSE, STOP)

    def test_pause_disappears_once_halted_stop_disappears_once_stopped(self):
        paused = apply_public_action(
            PublicActionRequest(PAUSE, "RUN-47"), _state()
        ).state
        assert contextual_actions(paused) == (STOP,)
        stopped = apply_public_action(
            PublicActionRequest(STOP, "RUN-47"), _state()
        ).state
        assert contextual_actions(stopped) == ()

    def test_authority_affordances_are_contextual_only(self):
        assert contextual_actions(_state(), authority_boundary=True) == (
            PAUSE,
            STOP,
            APPROVE,
        )
        assert contextual_actions(
            _state(), authority_boundary=True, merge_ready=True
        ) == (PAUSE, STOP, APPROVE, MERGE)

    def test_contextual_actions_never_leak_internal_verbs(self):
        for kwargs in ({}, {"authority_boundary": True}, {"merge_ready": True}):
            result = contextual_actions(_state(), **kwargs)
            assert not (set(result) & set(INTERNAL_RUNTIME_VERBS))
            assert set(result) <= set(PUBLIC_ACTIONS)


# ---------------------------------------------------------------- 2
class TestStopIsNotCancel:
    """WP3-2: STOP is first-class; it never aliases or becomes CANCEL."""

    def test_cancel_is_not_a_public_action(self):
        assert "CANCEL" not in PUBLIC_ACTIONS
        assert "CANCEL" in INTERNAL_RUNTIME_VERBS
        with pytest.raises(TaskControllerValidationError):
            PublicActionRequest("CANCEL", "RUN-47")

    def test_stop_disposition_is_stopped_never_cancelled(self):
        result = apply_public_action(PublicActionRequest(STOP, "RUN-47"), _state())
        assert result.disposition == Disposition.STOPPED
        assert result.disposition != "CANCELLED"
        assert "CANCELLED" not in Disposition.ALL
        assert "CANCELLED" in FORBIDDEN_DISPOSITIONS

    def test_stop_is_structurally_distinct_from_cancel(self):
        """No cancel alias/mapping exists in the STOP result path."""
        result = apply_public_action(PublicActionRequest(STOP, "RUN-47"), _state())
        flat = repr(result.to_dict()).upper().replace("CANCELLATION", "")
        assert "CANCEL" not in flat
        assert result.action == STOP and result.state.disposition == Disposition.STOPPED

    def test_stop_result_explicitly_denies_cancellation_semantics(self):
        result = apply_public_action(PublicActionRequest(STOP, "RUN-47"), _state())
        detail = result.detail.lower()
        assert "not a cancellation" in detail
        assert "not done" in detail

    def test_stop_is_not_destructive_state_is_intact(self):
        before = _state()
        result = apply_public_action(PublicActionRequest(STOP, "RUN-47"), before)
        after = result.state
        assert after.run_id == before.run_id
        assert after.evidence == before.evidence
        assert after.current_work_unit == before.current_work_unit
        assert after.stopped_at is not None
        assert after.paused_at is None


# ---------------------------------------------------------------- 3
class TestStopBlocksWorkAtSafeBoundary:
    """WP3-3: after STOP no new meaningful work unit may start."""

    def test_running_state_may_start_a_work_unit(self):
        state = _state()
        assert state.may_start_work_unit() is True
        started = start_work_unit(state, "S3")
        assert started.current_work_unit == "S3"
        assert started.revision == state.revision + 1

    def test_stop_blocks_the_next_work_unit_start(self):
        stopped = apply_public_action(
            PublicActionRequest(STOP, "RUN-47"), _state()
        ).state
        assert stopped.halted is True and stopped.may_start_work_unit() is False
        with pytest.raises(WorkUnitBlockedError):
            start_work_unit(stopped, "S3")

    def test_pause_also_blocks_the_next_work_unit_start(self):
        paused = apply_public_action(
            PublicActionRequest(PAUSE, "RUN-47"), _state()
        ).state
        assert paused.may_start_work_unit() is False
        with pytest.raises(WorkUnitBlockedError):
            start_work_unit(paused, "S3")

    def test_stop_records_the_exact_safe_boundary(self):
        result = apply_public_action(PublicActionRequest(STOP, "RUN-47"), _state())
        assert isinstance(result.boundary, SafeBoundary)
        assert result.boundary.work_unit_id == "S2"
        assert result.state.stopped_at == result.boundary

    def test_repeated_stop_is_idempotent_in_disposition(self):
        first = apply_public_action(PublicActionRequest(STOP, "RUN-47"), _state()).state
        second = apply_public_action(PublicActionRequest(STOP, "RUN-47"), first).state
        assert second.disposition == Disposition.STOPPED
        assert second.evidence == first.evidence

    def test_stop_fails_closed_when_no_safe_boundary_representable(self):
        no_unit = _state(current_work_unit=None)
        assert default_safe_boundary(no_unit) is None
        with pytest.raises(SafeBoundaryUnavailableError):
            apply_public_action(PublicActionRequest(STOP, "RUN-47"), no_unit)
        with pytest.raises(SafeBoundaryUnavailableError):
            apply_public_action(PublicActionRequest(PAUSE, "RUN-47"), no_unit)

    def test_injected_resolver_must_return_a_safe_boundary(self):
        with pytest.raises(TaskControllerValidationError):
            apply_public_action(
                PublicActionRequest(STOP, "RUN-47"),
                _state(),
                resolve_safe_boundary=lambda s: "end of S2",
            )

    def test_narrow_resolver_interface_can_represent_a_richer_boundary(self):
        """A richer adapter may be injected without activating deferred core."""
        result = apply_public_action(
            PublicActionRequest(STOP, "RUN-47"),
            _state(),
            resolve_safe_boundary=lambda s: SafeBoundary(
                work_unit_id="adapter-unit", description="adapter-provided boundary"
            ),
        )
        assert result.boundary.work_unit_id == "adapter-unit"
        assert result.state.disposition == Disposition.STOPPED

    def test_safe_boundary_fails_closed_on_blank_fields(self):
        with pytest.raises(TaskControllerValidationError):
            SafeBoundary(work_unit_id="", description="d")
        with pytest.raises(TaskControllerValidationError):
            SafeBoundary(work_unit_id="S1", description="  ")


# ---------------------------------------------------------------- 4
class TestNoFabricatedDoneAndEvidencePreserved:
    """WP3-4: evidence/state preserved; DONE can never be fabricated."""

    def test_dispositions_contain_no_completion_value(self):
        assert Disposition.ALL == ("RUNNING", "PAUSED", "STOPPED")
        for banned in FORBIDDEN_DISPOSITIONS:
            assert banned not in Disposition.ALL

    @pytest.mark.parametrize("action", (PAUSE, STOP, APPROVE, MERGE))
    def test_no_action_ever_yields_a_completion_disposition(self, action):
        result = apply_public_action(PublicActionRequest(action, "RUN-47"), _state())
        assert result.disposition in Disposition.ALL
        assert result.disposition not in FORBIDDEN_DISPOSITIONS

    def test_result_model_rejects_a_fabricated_done(self):
        for bad in FORBIDDEN_DISPOSITIONS:
            with pytest.raises(TaskControllerValidationError):
                PublicActionResult(
                    action=STOP,
                    run_id="RUN-47",
                    state=_state(),
                    disposition=bad,
                    detail="x",
                )

    @pytest.mark.parametrize("action", (PAUSE, STOP, APPROVE, MERGE))
    def test_evidence_is_never_dropped_or_rewritten(self, action):
        before = _state()
        result = apply_public_action(PublicActionRequest(action, "RUN-47"), before)
        assert result.state.evidence == before.evidence
        assert before.evidence == ("WP1 gate validated", "WP2 rootcard green")

    def test_pause_surfaces_paused_not_completion(self):
        result = apply_public_action(PublicActionRequest(PAUSE, "RUN-47"), _state())
        assert result.disposition == Disposition.PAUSED
        assert "no completion fabricated" in result.detail

    def test_state_is_immutable_and_transitions_are_additive(self):
        state = _state()
        with pytest.raises(dataclasses.FrozenInstanceError):
            state.disposition = Disposition.STOPPED  # type: ignore[misc]
        result = apply_public_action(PublicActionRequest(STOP, "RUN-47"), state)
        assert state.disposition == Disposition.RUNNING  # original untouched
        assert result.state is not state
        assert result.state.revision == state.revision + 1


# ---------------------------------------------------------------- 5
class TestFailClosed:
    """WP3-5: unknown actions, wrong run and stale requests fail closed."""

    @pytest.mark.parametrize(
        "bad",
        ("RESUME", "CANCEL", "REPLAN", "pause", "Stop", "stop", "DONE", "TERMINATE", ""),
    )
    def test_unknown_or_non_public_action_rejected(self, bad):
        with pytest.raises(TaskControllerValidationError):
            PublicActionRequest(bad, "RUN-47")
        with pytest.raises(TaskControllerValidationError):
            apply_public_action({"action": bad, "run_id": "RUN-47"}, _state())

    def test_blank_run_id_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            PublicActionRequest(STOP, "  ")

    def test_action_for_a_different_run_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            apply_public_action(PublicActionRequest(STOP, "RUN-99"), _state())

    def test_stale_expected_revision_rejected(self):
        with pytest.raises(StaleControlRequestError):
            apply_public_action(
                PublicActionRequest(STOP, "RUN-47", expected_revision=1), _state()
            )

    def test_current_expected_revision_accepted(self):
        result = apply_public_action(
            PublicActionRequest(STOP, "RUN-47", expected_revision=3), _state()
        )
        assert result.disposition == Disposition.STOPPED

    def test_stale_authority_request_also_fails_closed(self):
        with pytest.raises(StaleControlRequestError):
            apply_public_action(
                PublicActionRequest(APPROVE, "RUN-47", expected_revision=99), _state()
            )

    def test_malformed_payload_and_state_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            PublicActionRequest.from_payload(["not", "a", "mapping"])
        with pytest.raises(TaskControllerValidationError):
            apply_public_action(PublicActionRequest(STOP, "RUN-47"), {"run_id": "RUN-47"})
        with pytest.raises(TaskControllerValidationError):
            contextual_actions({"run_id": "RUN-47"})

    def test_malformed_state_fields_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            _state(disposition="DONE")
        with pytest.raises(TaskControllerValidationError):
            _state(evidence="bare string")
        with pytest.raises(TaskControllerValidationError):
            _state(evidence=("",))
        with pytest.raises(TaskControllerValidationError):
            _state(revision=-1)
        with pytest.raises(TaskControllerValidationError):
            _state(run_id=" ")
        with pytest.raises(TaskControllerValidationError):
            start_work_unit(_state(), "")


# ---------------------------------------------------------------- 6
class TestAuthorityOnlyActions:
    """WP3-6: APPROVE/MERGE are authority-required with zero mutation."""

    @pytest.mark.parametrize("action", (APPROVE, MERGE))
    def test_authority_required_and_no_mutation(self, action):
        state = _state()
        result = apply_public_action(PublicActionRequest(action, "RUN-47"), state)
        assert result.authority_required is True
        assert result.runtime_mutated is False
        assert result.state is state  # identity preserved: nothing mutated
        assert result.disposition == state.disposition
        assert result.state.revision == state.revision

    @pytest.mark.parametrize("action", (APPROVE, MERGE))
    def test_authority_detail_denies_approval_and_merge(self, action):
        result = apply_public_action(PublicActionRequest(action, "RUN-47"), _state())
        detail = result.detail.lower()
        assert "not approved" in detail and "not merged" in detail
        assert "runtime not mutated" in detail

    def test_control_actions_do_not_claim_authority(self):
        for action in CONTROL_ACTIONS:
            result = apply_public_action(PublicActionRequest(action, "RUN-47"), _state())
            assert result.authority_required is False

    def test_authority_flag_illegal_for_control_actions(self):
        with pytest.raises(TaskControllerValidationError):
            PublicActionResult(
                action=STOP,
                run_id="RUN-47",
                state=_state(),
                disposition=Disposition.STOPPED,
                detail="x",
                authority_required=True,
            )

    def test_result_can_never_report_a_runtime_mutation(self):
        with pytest.raises(TaskControllerValidationError):
            PublicActionResult(
                action=STOP,
                run_id="RUN-47",
                state=_state(),
                disposition=Disposition.STOPPED,
                detail="x",
                runtime_mutated=True,
            )

    def test_authority_action_does_not_halt_the_run(self):
        result = apply_public_action(PublicActionRequest(APPROVE, "RUN-47"), _state())
        assert result.state.may_start_work_unit() is True


# ---------------------------------------------------------------- 7
class TestInternalVerbsNeverPublic:
    """WP3-7: RESUME/CANCEL/REPLAN never appear in the default RootCard API."""

    def test_internal_verbs_are_declared_and_disjoint(self):
        assert INTERNAL_RUNTIME_VERBS == ("RESUME", "CANCEL", "REPLAN")
        assert not (set(INTERNAL_RUNTIME_VERBS) & set(PUBLIC_ACTIONS))

    def test_default_rootcard_payload_never_exposes_internal_verbs(self):
        cards = [
            _rootcard(),
            _rootcard(paused=True),
            _rootcard(authority_boundary=True),
            _rootcard(
                authority_boundary=True, merge_ready=True, pr="#53", head_sha="a36de7f7"
            ),
        ]
        for card in cards:
            payload = render_rootcard(card)
            assert set(payload["actions"]) <= set(PUBLIC_ACTIONS)
            flat = repr(payload).upper()
            for verb in INTERNAL_RUNTIME_VERBS:
                assert verb not in flat

    def test_richer_runtime_verbs_remain_available_internally(self):
        """The deferred Full-E2E surface keeps its richer verbs untouched."""
        from taskcontroller.projections.actions import (
            AUTHORITY_ACTIONS as RUNTIME_AUTHORITY,
            CONTROL_ACTIONS as RUNTIME_CONTROL,
        )

        assert RUNTIME_CONTROL == ("PAUSE", "RESUME", "CANCEL", "REPLAN")
        assert RUNTIME_AUTHORITY == ("APPROVE", "MERGE")
        # ...and they are NOT the MVP public API.
        assert RUNTIME_CONTROL != PUBLIC_ACTIONS


# ---------------------------------------------------------------- 8
class TestPurityAndNoDeferredCoreActivation:
    """WP3-8: the MVP default path activates no deferred Full-E2E core."""

    def test_no_deferred_core_import_in_the_mvp_action_module(self):
        tree = ast.parse(ACTIONS_SOURCE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        forbidden = (
            "taskcontroller.controlplane",
            "taskcontroller.runtime",
            "taskcontroller.projections",
            "taskcontroller.routing",
            "taskcontroller.execution",
            "taskcontroller.packs",
            "slack_sdk",
            "requests",
            "httpx",
            "socket",
            "subprocess",
            "time",
            "datetime",
            "random",
        )
        for mod in imported:
            assert not mod.startswith(forbidden), mod

    def test_mvp_package_import_does_not_pull_deferred_core(self):
        import subprocess
        import sys

        code = (
            "import sys; import taskcontroller.mvp as m; "
            "bad=[k for k in sys.modules if k.startswith(("
            "'taskcontroller.controlplane','taskcontroller.runtime',"
            "'taskcontroller.projections','taskcontroller.routing',"
            "'taskcontroller.execution','taskcontroller.packs'))]; "
            "print(','.join(sorted(bad)))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(Path(ACTIONS_SOURCE).parents[2]),
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "", out.stdout

    def test_no_wall_clock_polling_or_randomness(self):
        source = ACTIONS_SOURCE.read_text(encoding="utf-8")
        for banned in ("time.sleep", "datetime.now", "utcnow", "while True", "random."):
            assert banned not in source, banned

    def test_apply_is_deterministic(self):
        state = _state()
        first = apply_public_action(PublicActionRequest(STOP, "RUN-47"), state).to_dict()
        for _ in range(10):
            assert (
                apply_public_action(PublicActionRequest(STOP, "RUN-47"), state).to_dict()
                == first
            )
