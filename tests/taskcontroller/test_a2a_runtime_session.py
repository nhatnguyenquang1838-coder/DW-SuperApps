from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import continuation_from_envelope, parse_mailbox_comment, render_mailbox_comment


class FakeMailboxBackend:
    def __init__(self) -> None:
        self.refs = {
            "controller": "github://org/repo/issues/57#issuecomment-controller",
            "hermes-cloud": "github://org/repo/issues/57#issuecomment-executor",
        }
        self.bodies: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self.corrupt_controller_readback = False

    def ensure_mailbox(self, actor: str) -> str:
        self.calls.append(("ensure", actor))
        return self.refs[actor]

    def write_mailbox(self, mailbox_ref: str, body: str) -> None:
        self.calls.append(("write", mailbox_ref))
        self.bodies[mailbox_ref] = body

    def read_mailbox(self, mailbox_ref: str) -> str:
        self.calls.append(("read", mailbox_ref))
        body = self.bodies.get(mailbox_ref, "")
        if self.corrupt_controller_readback and mailbox_ref == self.refs["controller"]:
            return body.replace("Latest seq: 1", "Latest seq: 999")
        return body


def _runtime():
    spec = importlib.util.find_spec("taskcontroller.runtime.session")
    assert spec is not None, "canonical executable TaskController A2A runtime is missing"
    return importlib.import_module("taskcontroller.runtime.session")


def _boot(tmp_path: Path, backend: FakeMailboxBackend):
    runtime = _runtime()
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    session = runtime.boot_taskcontroller_session(
        continuation_store=audit,
        mailbox_backend=backend,
        run_id="run.a2a.1",
        node_id="node.1",
        controller_actor="controller",
        executor_actor="hermes-cloud",
        exact_head_sha="a" * 40,
        wakeup_binding="slack-websocket",
        request="Execute the bounded node.",
        updated_at="2026-08-25T00:10:00+07:00",
        human_root_ref="slack://C0BJSPXN7UN/1787569433.468359",
    )
    return runtime, audit, session


def test_registry_selects_executable_a2a_runtime_not_deferred_slack_pilot() -> None:
    root = Path(__file__).resolve().parents[2]
    registry = (root / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")

    assert "runtime_session: taskcontroller/runtime/session.py" in registry
    assert "full_e2e_runtime: active" in registry
    assert "full_e2e_runtime: deferred" not in registry
    assert "legacy_slack_pilot: compatibility-only" in registry


def test_legacy_mvp_slack_runtime_is_explicitly_compatibility_only() -> None:
    root = Path(__file__).resolve().parents[2]
    package = (root / "taskcontroller" / "mvp" / "__init__.py").read_text(encoding="utf-8")
    monitoring = (root / "taskcontroller" / "mvp" / "monitoring.py").read_text(encoding="utf-8")
    pilot = (root / "taskcontroller" / "mvp" / "pilot.py").read_text(encoding="utf-8")

    assert "taskcontroller/runtime/session.py" in package
    assert "compatibility-only" in package.lower()
    assert "LEGACY COMPATIBILITY ONLY" in monitoring
    assert "taskcontroller/runtime/session.py" in monitoring
    assert "LEGACY COMPATIBILITY ONLY" in pilot
    assert "taskcontroller/runtime/session.py" in pilot


def test_boot_materializes_both_mailboxes_persists_checkpoint_and_exact_readbacks(tmp_path: Path) -> None:
    backend = FakeMailboxBackend()
    runtime, audit, session = _boot(tmp_path, backend)

    assert backend.calls[:4] == [
        ("ensure", "controller"),
        ("ensure", "hermes-cloud"),
        ("write", backend.refs["controller"]),
        ("read", backend.refs["controller"]),
    ]
    assert session.checkpoint.controller_mailbox_ref == backend.refs["controller"]
    assert session.checkpoint.executor_mailbox_ref == backend.refs["hermes-cloud"]
    assert session.poll_target.mailbox_ref == backend.refs["hermes-cloud"]
    assert session.poll_target.expected_seq == 1

    controller_envelope = parse_mailbox_comment(backend.bodies[backend.refs["controller"]])
    embedded = continuation_from_envelope(controller_envelope)
    assert embedded == session.checkpoint
    assert controller_envelope.request == "Execute the bounded node."
    assert controller_envelope.state["head_sha"] == "a" * 40
    audit.close()


def test_boot_fails_closed_when_controller_mailbox_exact_readback_differs(tmp_path: Path) -> None:
    backend = FakeMailboxBackend()
    backend.corrupt_controller_readback = True
    runtime = _runtime()
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")

    with pytest.raises(TaskControllerValidationError, match="TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED"):
        runtime.boot_taskcontroller_session(
            continuation_store=audit,
            mailbox_backend=backend,
            run_id="run.a2a.bad-readback",
            node_id="node.1",
            controller_actor="controller",
            executor_actor="hermes-cloud",
            exact_head_sha="b" * 40,
            wakeup_binding="slack-websocket",
            request="Execute.",
            updated_at="2026-08-25T00:10:00+07:00",
        )
    audit.close()


def test_poll_reads_only_bound_executor_mailbox_and_accepts_exact_expected_seq(tmp_path: Path) -> None:
    backend = FakeMailboxBackend()
    runtime, audit, session = _boot(tmp_path, backend)

    executor_envelope = runtime.A2AEnvelope(
        run_id=session.checkpoint.run_id,
        node_id="node.1",
        sender="hermes-cloud",
        recipient="controller",
        seq=1,
        kind="REPORT",
        state={"status": "DONE", "head_sha": "a" * 40},
        updated_at="2026-08-25T00:11:00+07:00",
    )
    backend.bodies[backend.refs["hermes-cloud"]] = render_mailbox_comment(executor_envelope)
    before = len(backend.calls)

    observation = runtime.poll_executor_mailbox(
        continuation_store=audit,
        mailbox_backend=backend,
        session=session,
    )

    assert backend.calls[before:] == [("read", backend.refs["hermes-cloud"])]
    assert observation.status == "OBSERVED"
    assert observation.envelope == executor_envelope
    assert observation.session.checkpoint.last_seen_executor_seq == 1
    assert observation.session.checkpoint.phase == "REVIEW_EXECUTOR"
    assert observation.session.checkpoint.next_action == "REVIEW_EXECUTOR"
    audit.close()


def test_poll_ignores_stale_equal_seq_but_fails_closed_on_sequence_gap(tmp_path: Path) -> None:
    backend = FakeMailboxBackend()
    runtime, audit, session = _boot(tmp_path, backend)

    stale = runtime.A2AEnvelope(
        run_id=session.checkpoint.run_id,
        node_id="node.1",
        sender="hermes-cloud",
        recipient="controller",
        seq=1,
        kind="REPORT",
        state={"status": "DONE", "head_sha": "a" * 40},
        updated_at="2026-08-25T00:11:00+07:00",
    )
    backend.bodies[backend.refs["hermes-cloud"]] = render_mailbox_comment(stale)
    observed = runtime.poll_executor_mailbox(audit, backend, session)
    assert observed.status == "OBSERVED"

    stale_again = runtime.poll_executor_mailbox(audit, backend, observed.session)
    assert stale_again.status == "STALE"
    assert stale_again.session == observed.session

    waiting = runtime.dispatch_taskcontroller_command(
        continuation_store=audit,
        mailbox_backend=backend,
        session=observed.session,
        request="Continue bounded execution.",
        updated_at="2026-08-25T00:12:00+07:00",
    )
    gap = runtime.A2AEnvelope(
        run_id=waiting.checkpoint.run_id,
        node_id="node.1",
        sender="hermes-cloud",
        recipient="controller",
        seq=3,
        kind="REPORT",
        state={"status": "DONE", "head_sha": "a" * 40},
        updated_at="2026-08-25T00:13:00+07:00",
    )
    backend.bodies[backend.refs["hermes-cloud"]] = render_mailbox_comment(gap)
    with pytest.raises(TaskControllerValidationError, match="sequence gap"):
        runtime.poll_executor_mailbox(audit, backend, waiting)
    audit.close()


def test_recovery_uses_persisted_continuation_and_controller_mailbox_not_slack_history(tmp_path: Path) -> None:
    backend = FakeMailboxBackend()
    runtime, audit, session = _boot(tmp_path, backend)

    recovered = runtime.recover_taskcontroller_session(
        continuation_store=audit,
        mailbox_backend=backend,
        run_id=session.checkpoint.run_id,
        controller_actor="controller",
    )

    assert recovered == session
    assert recovered.poll_target.mailbox_ref == backend.refs["hermes-cloud"]
    assert not hasattr(recovered, "thread_history")
    assert not hasattr(recovered, "last_seen_ts")
    audit.close()
