import pytest
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.communication_v2 import (
    MARKER, CommunicationV2, create_next, next_seq, parse,
)

RUN = "scrum781-q0-fresh-20261010-r1"


def new(history=(), sender="GPT", recipient="Hermes", kind="COMMAND"):
    return create_next(history, run=RUN, sender=sender, recipient=recipient,
                       kind=kind, goal="Restore Q0 baseline and fixture",
                       next_action="Recover P1 source. Report exact refs/sha.",
                       source_ref="github://gwc/issues/595")


def test_human_readable_roundtrip_and_increasing_global_sequence():
    a = new()
    b = new((a.render(),), "Hermes", "GPT", "REPORT")
    c = new((a.render(), b.render()), kind="CORRECTION")
    assert [a.seq, b.seq, c.seq] == [1, 2, 3]
    assert all(parse(x.render()) == x for x in (a, b, c))
    assert "lease" not in a.render().lower()
    assert next_seq((a.render(), b.render(), c.render()), run=RUN) == 4


def test_unrelated_comments_ignore_and_gaps_reject():
    a = new()
    assert next_seq(("arbitrary #595 human note", a.render()), run=RUN) == 2
    tampered = a.render().replace("seq: 1", "seq: 3")
    with pytest.raises(TaskControllerValidationError):
        next_seq((tampered,), run=RUN)


def test_marker_malformed_refused_no_silent_accept():
    with pytest.raises(TaskControllerValidationError):
        parse(MARKER + "\nhello")


def test_payload_is_instruction_only_not_protected_authority():
    a = new()
    assert "execution_identity" not in a.render()
    assert "fencing_token" not in a.render()
    assert "**NEXT**" in a.render()


def test_sanitize_header_and_self_message():
    with pytest.raises(TaskControllerValidationError):
        new(sender="GPT", recipient="GPT")
    with pytest.raises(TaskControllerValidationError):
        new(sender="GPT\nlease: FAKE")
