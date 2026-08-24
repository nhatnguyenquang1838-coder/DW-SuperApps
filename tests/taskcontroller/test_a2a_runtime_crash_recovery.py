from __future__ import annotations

from pathlib import Path

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import continuation_from_envelope, parse_mailbox_comment, render_mailbox_comment
from taskcontroller.runtime import session as runtime


class FaultMailboxBackend:
    def __init__(self) -> None:
        self.refs = {
            "controller": "github://org/repo/issues/88#controller",
            "hermes-cloud": "github://org/repo/issues/88#executor",
        }
        self.bodies: dict[str, str] = {}
        self.fail_next_controller_write = False

    def ensure_mailbox(self, actor: str) -> str:
        return self.refs[actor]

    def write_mailbox(self, mailbox_ref: str, body: str) -> None:
        if self.fail_next_controller_write and mailbox_ref == self.refs["controller"]:
            self.fail_next_controller_write = False
            raise RuntimeError("simulated controller mailbox write interruption")
        self.bodies[mailbox_ref] = body

    def read_mailbox(self, mailbox_ref: str) -> str:
        return self.bodies.get(mailbox_ref, "")


def _boot(tmp_path: Path, backend: FaultMailboxBackend):
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    session = runtime.boot_taskcontroller_session(
        continuation_store=audit,
        mailbox_backend=backend,
        run_id="run.crash.1",
        node_id="node.1",
        controller_actor="controller",
        executor_actor="hermes-cloud",
        exact_head_sha="c" * 40,
        wakeup_binding="slack-websocket",
        request="Execute bounded work.",
        updated_at="2026-08-25T00:40:00+07:00",
    )
    return audit, session


def _executor_report(session, seq: int = 1):
    return runtime.A2AEnvelope(
        run_id=session.checkpoint.run_id,
        node_id="node.1",
        sender="hermes-cloud",
        recipient="controller",
        seq=seq,
        kind="REPORT",
        state={"status": "DONE", "head_sha": "c" * 40},
        updated_at="2026-08-25T00:41:00+07:00",
    )


def test_recovery_repairs_stale_controller_mailbox_after_observation_sync_interruption(tmp_path: Path) -> None:
    backend = FaultMailboxBackend()
    audit, session = _boot(tmp_path, backend)
    backend.bodies[backend.refs["hermes-cloud"]] = render_mailbox_comment(_executor_report(session))
    backend.fail_next_controller_write = True

    with pytest.raises(TaskControllerValidationError, match="TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED"):
        runtime.poll_executor_mailbox(audit, backend, session)

    # The ledger advanced after observing the Executor, but the process died
    # before the Controller mailbox copy could be rewritten. Recovery must use
    # the durable REVIEW_EXECUTOR checkpoint to repair that stale copy.
    recovered = runtime.recover_taskcontroller_session(
        continuation_store=audit,
        mailbox_backend=backend,
        run_id=session.checkpoint.run_id,
        controller_actor="controller",
    )
    assert recovered.checkpoint.phase == "REVIEW_EXECUTOR"
    assert recovered.checkpoint.last_seen_executor_seq == 1
    embedded = continuation_from_envelope(
        parse_mailbox_comment(backend.bodies[backend.refs["controller"]])
    )
    assert embedded == recovered.checkpoint
    audit.close()


def test_recovery_rolls_back_unmaterialized_dispatch_checkpoint(tmp_path: Path) -> None:
    backend = FaultMailboxBackend()
    audit, session = _boot(tmp_path, backend)
    backend.bodies[backend.refs["hermes-cloud"]] = render_mailbox_comment(_executor_report(session))
    observed = runtime.poll_executor_mailbox(audit, backend, session).session
    assert observed.checkpoint.phase == "REVIEW_EXECUTOR"

    backend.fail_next_controller_write = True
    with pytest.raises(TaskControllerValidationError, match="TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED"):
        runtime.dispatch_taskcontroller_command(
            continuation_store=audit,
            mailbox_backend=backend,
            session=observed,
            request="Continue bounded work.",
            updated_at="2026-08-25T00:42:00+07:00",
        )

    # Persist-before-dispatch may have recorded WAIT_EXECUTOR/seq+1, but because
    # the new command never materialized in the Controller mailbox and therefore
    # cannot have been safely woken, recovery must restore the last materialized
    # REVIEW_EXECUTOR boundary instead of fabricating or polling a missing command.
    recovered = runtime.recover_taskcontroller_session(
        continuation_store=audit,
        mailbox_backend=backend,
        run_id=observed.checkpoint.run_id,
        controller_actor="controller",
    )
    assert recovered == observed

    # Re-read proves the durable continuation was reconciled too, not merely the
    # in-memory return object.
    recovered_again = runtime.recover_taskcontroller_session(
        continuation_store=audit,
        mailbox_backend=backend,
        run_id=observed.checkpoint.run_id,
        controller_actor="controller",
    )
    assert recovered_again == observed
    audit.close()
