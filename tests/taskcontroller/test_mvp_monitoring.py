"""WP4 (#51) focused tests — MVP 60s in-session Controller monitoring loop.

Proves: exact 60s default cadence with an injected fake sleeper (zero real
sleep), strict newer-than-last_seen_ts reading with duplicate/older replies
ignored, silent polling, RootCard updates only on material change, verdict
routing (CONTINUE keeps monitoring; WAIT_CONTROLLER / INTERCEPT / TERMINAL stop
at the boundary), TERMINAL is not runtime DONE and grants no authority,
malformed reports fail closed, the five intercept reasons only, and no
scheduler / deferred Full-E2E dependency.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp import monitoring as mon
from taskcontroller.mvp.monitoring import (
    BOUNDARY_VERDICTS,
    POLL_INTERVAL_SECONDS,
    REASON_BOUNDARY,
    REASON_MAX_POLLS,
    LoopObservation,
    LoopOutcome,
    MalformedReportError,
    ThreadReply,
    run_monitoring_loop,
)
from taskcontroller.mvp.protocol_bridge import (
    CONTINUE,
    INTERCEPT,
    TERMINAL,
    WAIT_CONTROLLER,
    ContractedSubtask,
    InterceptReason,
)

MONITORING_SOURCE = Path(mon.__file__)


def _contract(subtask_id: str = "S1", after_report: str = CONTINUE) -> ContractedSubtask:
    return ContractedSubtask(
        subtask_id=subtask_id,
        objective=f"objective for {subtask_id}",
        allowed_work=("bounded work",),
        expected_output=("artifact",),
        report_requirement=("evidence in the thread reply",),
        after_report=after_report,
    )


def _payload(**overrides):
    base = dict(
        subtask_id="S1",
        status="RUNNING",
        completed=["unit finished"],
        evidence=["exact evidence"],
        next_action="await controller",
        after=CONTINUE,
    )
    base.update(overrides)
    return base


class FakeSleeper:
    """Injected sleeper. Records cadences; never really sleeps."""

    def __init__(self):
        self.calls: list[int] = []

    def __call__(self, seconds: int) -> None:
        self.calls.append(seconds)


class FakeReader:
    """Injected reply reader. Serves scripted batches per poll."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.cursors: list[str | None] = []
        self.poll = 0

    def __call__(self, last_seen_ts):
        self.cursors.append(last_seen_ts)
        batch = self.batches[self.poll] if self.poll < len(self.batches) else []
        self.poll += 1
        return batch


class FakeUpdater:
    """Injected RootCard updater. Records material updates only."""

    def __init__(self):
        self.updates: list[LoopObservation] = []

    def __call__(self, observation: LoopObservation) -> None:
        self.updates.append(observation)


# ---------------------------------------------------------------- 1
class TestCadenceAndZeroRealSleep:
    """WP4-1: default cadence is exactly 60s; unit tests never really sleep."""

    def test_default_cadence_is_exactly_sixty_seconds(self):
        assert POLL_INTERVAL_SECONDS == 60

    def test_loop_sleeps_the_default_cadence_via_injected_sleeper(self):
        sleeper = FakeSleeper()
        run_monitoring_loop(
            _contract(),
            read_replies=FakeReader([[]]),
            sleeper=sleeper,
            max_polls=1,
        )
        assert sleeper.calls == [60]

    def test_no_real_sleep_happens_in_this_test_suite(self):
        sleeper = FakeSleeper()
        started = time.monotonic()
        run_monitoring_loop(
            _contract(),
            read_replies=FakeReader([[], [], []]),
            sleeper=sleeper,
            max_polls=3,
        )
        assert sleeper.calls == [60, 60, 60]
        assert time.monotonic() - started < 1.0

    def test_cadence_is_overridable_for_tests_only(self):
        sleeper = FakeSleeper()
        run_monitoring_loop(
            _contract(),
            read_replies=FakeReader([[]]),
            sleeper=sleeper,
            max_polls=1,
            poll_interval_seconds=5,
        )
        assert sleeper.calls == [5]

    @pytest.mark.parametrize("bad", (0, -1, 1.5, True, "60"))
    def test_invalid_cadence_rejected(self, bad):
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(
                _contract(),
                read_replies=FakeReader([[]]),
                sleeper=FakeSleeper(),
                poll_interval_seconds=bad,
            )

    @pytest.mark.parametrize("bad", (0, -3, 1.5, True))
    def test_invalid_max_polls_rejected(self, bad):
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(
                _contract(),
                read_replies=FakeReader([[]]),
                sleeper=FakeSleeper(),
                max_polls=bad,
            )


# ---------------------------------------------------------------- 2
class TestLastSeenTsDiscipline:
    """WP4-2: only strictly newer replies; duplicates/older ignored."""

    def test_reader_receives_the_explicit_cursor(self):
        reader = FakeReader([[], []])
        run_monitoring_loop(
            _contract(),
            read_replies=reader,
            sleeper=FakeSleeper(),
            last_seen_ts="100.0",
            max_polls=2,
        )
        assert reader.cursors == ["100.0", "100.0"]

    def test_older_and_equal_replies_are_ignored(self):
        reader = FakeReader(
            [[ThreadReply("100.0", _payload()), ThreadReply("99.0", _payload())]]
        )
        updater = FakeUpdater()
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=reader,
            sleeper=FakeSleeper(),
            last_seen_ts="100.0",
            max_polls=1,
            update_rootcard=updater,
        )
        assert outcome.observations == ()
        assert updater.updates == []
        assert outcome.last_seen_ts == "100.0"

    def test_duplicate_ts_in_one_batch_is_processed_once(self):
        reply = ThreadReply("101.0", _payload())
        updater = FakeUpdater()
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=FakeReader([[reply, reply]]),
            sleeper=FakeSleeper(),
            last_seen_ts="100.0",
            max_polls=1,
            update_rootcard=updater,
        )
        assert len(outcome.observations) == 1
        assert len(updater.updates) == 1

    def test_ts_ordering_is_numeric_not_lexicographic(self):
        """Regression: "99.0" must NOT be treated as newer than "100.0"."""
        updater = FakeUpdater()
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=FakeReader(
                [
                    [
                        ThreadReply("100.5", _payload(evidence=["b"])),
                        ThreadReply("99.0", _payload(evidence=["a"])),
                        ThreadReply("1000.0", _payload(evidence=["c"])),
                    ]
                ]
            ),
            sleeper=FakeSleeper(),
            last_seen_ts="100.0",
            max_polls=1,
            update_rootcard=updater,
        )
        assert [u.reply_ts for u in updater.updates] == ["100.5", "1000.0"]
        assert outcome.last_seen_ts == "1000.0"

    def test_cursor_advances_to_the_newest_processed_reply(self):
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=FakeReader(
                [[ThreadReply("101.0", _payload()), ThreadReply("102.0", _payload())]]
            ),
            sleeper=FakeSleeper(),
            last_seen_ts="100.0",
            max_polls=1,
        )
        assert outcome.last_seen_ts == "102.0"

    def test_replies_are_processed_in_ascending_ts_order(self):
        updater = FakeUpdater()
        run_monitoring_loop(
            _contract(),
            read_replies=FakeReader(
                [
                    [
                        ThreadReply("103.0", _payload(evidence=["c"])),
                        ThreadReply("101.0", _payload(evidence=["a"])),
                        ThreadReply("102.0", _payload(evidence=["b"])),
                    ]
                ]
            ),
            sleeper=FakeSleeper(),
            last_seen_ts="100.0",
            max_polls=1,
            update_rootcard=updater,
        )
        assert [u.reply_ts for u in updater.updates] == ["101.0", "102.0", "103.0"]

    def test_no_cursor_reads_everything(self):
        reader = FakeReader([[ThreadReply("1.0", _payload())]])
        outcome = run_monitoring_loop(
            _contract(), read_replies=reader, sleeper=FakeSleeper(), max_polls=1
        )
        assert reader.cursors == [None]
        assert outcome.last_seen_ts == "1.0"

    @pytest.mark.parametrize("bad", ("", "   "))
    def test_blank_cursor_rejected(self, bad):
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(
                _contract(),
                read_replies=FakeReader([[]]),
                sleeper=FakeSleeper(),
                last_seen_ts=bad,
            )

    def test_thread_reply_fails_closed_on_bad_shape(self):
        with pytest.raises(TaskControllerValidationError):
            ThreadReply("", _payload())
        with pytest.raises(TaskControllerValidationError):
            ThreadReply("101.0", ["not", "a", "mapping"])

    def test_reader_must_return_thread_replies(self):
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(
                _contract(),
                read_replies=lambda ts: [{"ts": "101.0"}],
                sleeper=FakeSleeper(),
            )
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(
                _contract(), read_replies=lambda ts: "nope", sleeper=FakeSleeper()
            )


# ---------------------------------------------------------------- 3
class TestSilentPollingAndMaterialUpdatesOnly:
    """WP4-3: polling emits nothing; RootCard updates only on material change."""

    def test_empty_polls_are_completely_silent(self):
        updater = FakeUpdater()
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=FakeReader([[], [], []]),
            sleeper=FakeSleeper(),
            max_polls=3,
            update_rootcard=updater,
        )
        assert updater.updates == []
        assert outcome.observations == ()
        assert outcome.reason == REASON_MAX_POLLS
        assert outcome.verdict is None

    def test_default_updater_is_a_silent_noop(self):
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=FakeReader([[ThreadReply("101.0", _payload())]]),
            sleeper=FakeSleeper(),
            max_polls=1,
        )
        assert len(outcome.observations) == 1  # observed, but nothing emitted

    def test_identical_repeated_report_is_not_a_material_update(self):
        payload = _payload()
        updater = FakeUpdater()
        outcome = run_monitoring_loop(
            _contract(),
            read_replies=FakeReader(
                [
                    [ThreadReply("101.0", payload)],
                    [ThreadReply("102.0", payload)],
                    [ThreadReply("103.0", payload)],
                ]
            ),
            sleeper=FakeSleeper(),
            max_polls=3,
            update_rootcard=updater,
        )
        assert len(updater.updates) == 1
        assert len(outcome.observations) == 1
        assert outcome.polls == 3

    def test_changed_evidence_is_a_material_update(self):
        updater = FakeUpdater()
        run_monitoring_loop(
            _contract(),
            read_replies=FakeReader(
                [
                    [ThreadReply("101.0", _payload(evidence=["e1"]))],
                    [ThreadReply("102.0", _payload(evidence=["e1", "e2"]))],
                ]
            ),
            sleeper=FakeSleeper(),
            max_polls=2,
            update_rootcard=updater,
        )
        assert [u.evidence for u in updater.updates] == [("e1",), ("e1", "e2")]

    def test_changed_verdict_is_a_material_update(self):
        updater = FakeUpdater()
        outcome = run_monitoring_loop(
            _contract("S1", CONTINUE),
            read_replies=FakeReader(
                [
                    [ThreadReply("101.0", _payload())],
                    [ThreadReply("102.0", _payload(status="BLOCKED"))],
                ]
            ),
            sleeper=FakeSleeper(),
            max_polls=2,
            update_rootcard=updater,
        )
        assert [u.verdict.verdict for u in updater.updates] == [CONTINUE, TERMINAL]
        assert outcome.verdict == TERMINAL


# ---------------------------------------------------------------- 4
class TestVerdictRouting:
    """WP4-4: CONTINUE keeps monitoring; boundaries return immediately."""

    def test_continue_keeps_monitoring_across_polls(self):
        sleeper = FakeSleeper()
        outcome = run_monitoring_loop(
            _contract("S1", CONTINUE),
            read_replies=FakeReader(
                [
                    [ThreadReply("101.0", _payload(evidence=["a"]))],
                    [ThreadReply("102.0", _payload(evidence=["b"]))],
                    [ThreadReply("103.0", _payload(evidence=["c"]))],
                ]
            ),
            sleeper=sleeper,
            max_polls=3,
        )
        assert outcome.verdict == CONTINUE
        assert outcome.reason == REASON_MAX_POLLS
        assert outcome.polls == 3 and sleeper.calls == [60, 60, 60]
        assert outcome.is_boundary is False

    def test_wait_controller_returns_the_review_boundary(self):
        sleeper = FakeSleeper()
        outcome = run_monitoring_loop(
            _contract("S1", WAIT_CONTROLLER),
            read_replies=FakeReader(
                [[ThreadReply("101.0", _payload(after=WAIT_CONTROLLER))], [ThreadReply("102.0", _payload())]]
            ),
            sleeper=sleeper,
            max_polls=5,
        )
        assert outcome.verdict == WAIT_CONTROLLER
        assert outcome.reason == REASON_BOUNDARY
        assert outcome.polls == 1 and sleeper.calls == [60]  # stopped at boundary
        assert outcome.is_boundary is True

    def test_intercept_returns_the_bounded_drift_boundary(self):
        outcome = run_monitoring_loop(
            _contract("S1", CONTINUE),
            read_replies=FakeReader([[ThreadReply("101.0", _payload(subtask_id="S9"))]]),
            sleeper=FakeSleeper(),
            max_polls=5,
        )
        assert outcome.verdict == INTERCEPT
        assert outcome.reason == REASON_BOUNDARY
        assert outcome.polls == 1
        assert outcome.observations[-1].verdict.intercept_reason == InterceptReason.SCOPE_DRIFT

    def test_terminal_closes_the_delegated_segment_only(self):
        outcome = run_monitoring_loop(
            _contract("S1", TERMINAL),
            read_replies=FakeReader([[ThreadReply("101.0", _payload(after=TERMINAL))]]),
            sleeper=FakeSleeper(),
            max_polls=5,
        )
        assert outcome.verdict == TERMINAL
        assert outcome.delegated_segment_closed is True
        assert outcome.runtime_done is False
        assert outcome.grants_authority is False

    def test_boundary_verdicts_are_exactly_three(self):
        assert BOUNDARY_VERDICTS == (WAIT_CONTROLLER, INTERCEPT, TERMINAL)
        assert CONTINUE not in BOUNDARY_VERDICTS

    def test_no_further_replies_are_read_after_a_boundary(self):
        reader = FakeReader(
            [
                [ThreadReply("101.0", _payload(after=WAIT_CONTROLLER))],
                [ThreadReply("102.0", _payload())],
            ]
        )
        run_monitoring_loop(
            _contract("S1", WAIT_CONTROLLER),
            read_replies=reader,
            sleeper=FakeSleeper(),
            max_polls=5,
        )
        assert reader.poll == 1  # the second batch was never read

    def test_all_five_intercept_reasons_are_reachable_and_bounded(self):
        cases = {
            InterceptReason.SCOPE_DRIFT: _payload(subtask_id="S9"),
            InterceptReason.AUTHORITY_DRIFT: _payload(authority_required=True),
            InterceptReason.PLAN_DRIFT: _payload(after=TERMINAL),
            InterceptReason.EVIDENCE_CONFLICT: _payload(evidence_conflict=True),
            InterceptReason.MATERIAL_FINDING: _payload(material_finding=True),
        }
        for reason, payload in cases.items():
            outcome = run_monitoring_loop(
                _contract("S1", CONTINUE),
                read_replies=FakeReader([[ThreadReply("101.0", payload)]]),
                sleeper=FakeSleeper(),
                max_polls=1,
            )
            assert outcome.verdict == INTERCEPT
            assert outcome.observations[-1].verdict.intercept_reason == reason

    def test_ordinary_progress_and_retries_are_not_intercept(self):
        """Tool choice / retry / normal runtime never produce an INTERCEPT."""
        for payload in (
            _payload(status="RUNNING", completed=["retried a transient step"]),
            _payload(status="RUNNING", completed=["chose a different tool"]),
            _payload(status="DONE", completed=["finished the contracted unit"]),
        ):
            outcome = run_monitoring_loop(
                _contract("S1", CONTINUE),
                read_replies=FakeReader([[ThreadReply("101.0", payload)]]),
                sleeper=FakeSleeper(),
                max_polls=1,
            )
            assert outcome.verdict == CONTINUE

    def test_outcome_model_fails_closed_on_bad_values(self):
        with pytest.raises(TaskControllerValidationError):
            LoopOutcome(verdict="DONE", reason=REASON_BOUNDARY, polls=1, last_seen_ts=None)
        with pytest.raises(TaskControllerValidationError):
            LoopOutcome(verdict=CONTINUE, reason="whatever", polls=1, last_seen_ts=None)
        with pytest.raises(TaskControllerValidationError):
            LoopOutcome(verdict=CONTINUE, reason=REASON_BOUNDARY, polls=-1, last_seen_ts=None)


# ---------------------------------------------------------------- 5
class TestMalformedReportFailsClosed:
    """WP4-5: a malformed report never degrades to CONTINUE."""

    @pytest.mark.parametrize(
        "bad",
        (
            {},
            {"subtask_id": "S1"},
            _payload(status="MAYBE"),
            _payload(after="ESCALATE"),
            _payload(evidence=[]),
            _payload(completed=[]),
            _payload(next_action=""),
            _payload(subtask_id=""),
        ),
    )
    def test_malformed_payload_raises_and_does_not_continue(self, bad):
        with pytest.raises(MalformedReportError):
            run_monitoring_loop(
                _contract(),
                read_replies=FakeReader([[ThreadReply("101.0", bad)]]),
                sleeper=FakeSleeper(),
                max_polls=1,
            )

    def test_malformed_error_is_a_validation_error_not_a_verdict(self):
        assert issubclass(MalformedReportError, TaskControllerValidationError)

    def test_bad_contract_reader_sleeper_updater_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop({"subtask_id": "S1"}, FakeReader([[]]), FakeSleeper())
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(_contract(), "not-callable", FakeSleeper())
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(_contract(), FakeReader([[]]), "not-callable")
        with pytest.raises(TaskControllerValidationError):
            run_monitoring_loop(
                _contract(), FakeReader([[]]), FakeSleeper(), update_rootcard="nope"
            )


# ---------------------------------------------------------------- 6
class TestLoopIsNotASchedulerAndStaysPure:
    """WP4-6: in-session only; no scheduler/automation or deferred-core import."""

    def test_no_scheduler_automation_or_deferred_core_import(self):
        tree = ast.parse(MONITORING_SOURCE.read_text(encoding="utf-8"))
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
            "threading",
            "asyncio",
            "multiprocessing",
            "concurrent",
            "subprocess",
            "sched",
            "signal",
            "socket",
            "slack_sdk",
            "requests",
            "httpx",
            "time",
            "datetime",
            "random",
            "crontab",
            "apscheduler",
        )
        for mod in imported:
            assert not mod.startswith(forbidden), mod

    def test_no_detached_execution_or_real_sleep_in_the_module(self):
        source = MONITORING_SOURCE.read_text(encoding="utf-8")
        for banned in (
            "time.sleep",
            "Thread(",
            "Process(",
            "asyncio.",
            "await ",
            "Popen",
            "os.fork",
            "spawn",
            "datetime.now",
            "random.",
        ):
            assert banned not in source, banned

    def test_mvp_import_surface_stays_free_of_deferred_core(self):
        import subprocess
        import sys

        code = (
            "import sys; import taskcontroller.mvp.monitoring as m; "
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
            cwd=str(MONITORING_SOURCE.parents[2]),
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == ""

    def test_loop_returns_synchronously_and_is_deterministic(self):
        def make():
            return run_monitoring_loop(
                _contract("S1", WAIT_CONTROLLER),
                read_replies=FakeReader([[ThreadReply("101.0", _payload(after=WAIT_CONTROLLER))]]),
                sleeper=FakeSleeper(),
                max_polls=3,
            )

        first = make().to_dict()
        for _ in range(5):
            assert make().to_dict() == first

    def test_transport_reading_stays_behind_the_injected_callable(self):
        """The engine calls the reader; it never builds a client itself."""
        source = MONITORING_SOURCE.read_text(encoding="utf-8")
        assert "class ReplyReader(Protocol)" in source
        for banned in ("WebClient", "chat_postMessage", "conversations_replies", "urlopen"):
            assert banned not in source, banned
