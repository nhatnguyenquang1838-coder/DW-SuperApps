"""GWC SCRUM-781: v1-style peer conversation must not depend on v2 leases."""
import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.peer_command_stream import (
    build_next_peer_command, unread_after, verify_peer_history,
)


NOW = "2026-10-12T20:30:00+07:00"
RUN = "scrum781-q0-fresh-20261010-r1"


def make(history=(), sender="gpt", recipient="hermes", kind="COMMAND"):
    return build_next_peer_command(
        history=history, run_id=RUN, node_id="SCRUM-781",
        sender=sender, recipient=recipient, kind=kind,
        request="Recover Q0 P1 baseline and original incident fixture; report exact refs",
        updated_at=NOW,
        artifact_refs=("github://nhatnguyenquang1838-coder/gwc/issues/595",),
    )


def test_every_exchange_increases_global_seq_without_lease():
    c1 = make()
    e2 = make((c1,), sender="hermes", recipient="gpt", kind="REPORT")
    c3 = make((c1, e2), kind="CORRECTION")
    assert (c1.seq, e2.seq, c3.seq) == (1, 2, 3)
    assert verify_peer_history((c1, e2, c3), run_id=RUN) == 3
    assert all("execution_identity" not in e.to_dict() for e in (c1, e2, c3))


def test_unread_observation_does_not_mutate_consumed_cursor():
    c1 = make()
    e2 = make((c1,), sender="hermes", recipient="gpt", kind="REPORT")
    assert unread_after((c1, e2), run_id=RUN, consumed_seq=0, recipient="hermes") == (c1,)
    assert unread_after((c1, e2), run_id=RUN, consumed_seq=1, recipient="hermes") == ()


def test_gap_or_duplicate_fails_closed_only_for_peer_stream():
    c1 = make()
    e2 = make((c1,), sender="hermes", recipient="gpt", kind="REPORT")
    with pytest.raises(TaskControllerValidationError, match="gap/fork"):
        verify_peer_history((c1, c1), run_id=RUN)
    with pytest.raises(TaskControllerValidationError, match="gap/fork"):
        verify_peer_history((e2,), run_id=RUN)


def test_native_source_drift_is_not_a_v1_command_gate():
    c1 = make()
    c2 = make((c1,), sender="hermes", recipient="gpt", kind="REPORT")
    assert c2.seq == 2


def test_no_self_message_and_no_empty_request():
    with pytest.raises(TaskControllerValidationError):
        make(sender="hermes", recipient="hermes")
    with pytest.raises(TaskControllerValidationError):
        build_next_peer_command(
            history=(), run_id=RUN, node_id="SCRUM-781", sender="gpt",
            recipient="hermes", kind="COMMAND", request=" ", updated_at=NOW
        )
