"""TC-MBX-108: universal state-advancing write predicate tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
)
from taskcontroller.interaction.state_advancement import (
    StateAdvancingDisposition,
    validate_state_advancing_write,
)


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"


@pytest.fixture
def envelopes() -> dict[str, V2MailboxEnvelope]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        name: V2MailboxEnvelope.from_dict(copy.deepcopy(fixture["cases"][name]))
        for name in ("child_result", "mixer_result", "terminal_result")
    }


def _current_identity(envelope: V2MailboxEnvelope) -> dict[str, Any]:
    identity = envelope.execution_identity
    return {
        "run_id": identity["run_id"],
        "node_id": identity["node_id"],
        "plan_version": identity["plan_version"],
        "attempt_id": identity["attempt_id"],
        "lease_generation": identity["lease_generation"],
        "contract_digest": identity["contract_digest"],
        "source_digest": identity["source_digest"],
    }


@pytest.mark.parametrize(
    ("fixture_name", "write_kind"),
    (
        ("child_result", "child_result"),
        ("mixer_result", "mixer_result"),
        ("terminal_result", "terminal_result"),
    ),
)
def test_one_validator_accepts_each_state_advancing_write_kind(
    envelopes: dict[str, V2MailboxEnvelope],
    fixture_name: str,
    write_kind: str,
) -> None:
    envelope = envelopes[fixture_name]
    decision = validate_state_advancing_write(
        envelope,
        current_identity=_current_identity(envelope),
        expected_source_digest=envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind=write_kind,
    )

    assert decision.disposition == StateAdvancingDisposition.ACCEPTED
    assert decision.advances_state is True
    assert decision.evidence_only is False
    assert decision.failed_checks == ()
    assert decision.write_kind == write_kind


@pytest.mark.parametrize(
    ("fixture_name", "write_kind"),
    (
        ("child_result", "child_result"),
        ("mixer_result", "mixer_result"),
        ("terminal_result", "terminal_result"),
    ),
)
def test_stale_generation_is_evidence_only_for_all_write_kinds(
    envelopes: dict[str, V2MailboxEnvelope],
    fixture_name: str,
    write_kind: str,
) -> None:
    envelope = envelopes[fixture_name]
    current = _current_identity(envelope)
    current["lease_generation"] += 1
    before = copy.deepcopy(current)

    decision = validate_state_advancing_write(
        envelope,
        current_identity=current,
        expected_source_digest=envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind=write_kind,
    )

    assert decision.disposition == MailboxV2ErrorCode.STALE_RESULT
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("lease_generation",)
    assert current == before


@pytest.mark.parametrize(
    "identity_field",
    (
        "run_id",
        "node_id",
        "plan_version",
        "attempt_id",
        "lease_generation",
        "contract_digest",
    ),
)
def test_each_current_identity_mismatch_is_stale_and_non_advancing(
    envelopes: dict[str, V2MailboxEnvelope],
    identity_field: str,
) -> None:
    envelope = envelopes["terminal_result"]
    current = _current_identity(envelope)
    if identity_field == "lease_generation":
        current[identity_field] += 1
    else:
        current[identity_field] = f"different-{identity_field}"

    decision = validate_state_advancing_write(
        envelope,
        current_identity=current,
        expected_source_digest=envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
    )

    assert decision.disposition == StateAdvancingDisposition.STALE_RESULT
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == (identity_field,)


def test_source_digest_mismatch_is_stale_and_non_advancing(
    envelopes: dict[str, V2MailboxEnvelope],
) -> None:
    envelope = envelopes["child_result"]
    decision = validate_state_advancing_write(
        envelope,
        current_identity=_current_identity(envelope),
        expected_source_digest="sha256:" + "0" * 64,
        actor_cursor=-1,
        write_kind="child_result",
    )

    assert decision.disposition == StateAdvancingDisposition.STALE_RESULT
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("source_digest",)


def test_non_new_actor_sequence_is_stale_and_non_advancing(
    envelopes: dict[str, V2MailboxEnvelope],
) -> None:
    envelope = envelopes["mixer_result"]
    decision = validate_state_advancing_write(
        envelope,
        current_identity=_current_identity(envelope),
        expected_source_digest=envelope.execution_identity["source_digest"],
        actor_cursor=envelope.seq,
        write_kind="mixer_result",
    )

    assert decision.disposition == StateAdvancingDisposition.STALE_RESULT
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("seq",)


def test_wrong_write_kind_message_pairing_fails_closed(
    envelopes: dict[str, V2MailboxEnvelope],
) -> None:
    envelope = envelopes["child_result"]

    with pytest.raises(MailboxV2ValidationError) as caught:
        validate_state_advancing_write(
            envelope,
            current_identity=_current_identity(envelope),
            expected_source_digest=envelope.execution_identity["source_digest"],
            actor_cursor=-1,
            write_kind="mixer_result",
        )

    assert caught.value.code == MailboxV2ErrorCode.CONTRACT_MISMATCH


def test_missing_current_identity_fails_closed_before_evaluation(
    envelopes: dict[str, V2MailboxEnvelope],
) -> None:
    envelope = envelopes["terminal_result"]
    current = _current_identity(envelope)
    del current["attempt_id"]

    with pytest.raises(MailboxV2ValidationError) as caught:
        validate_state_advancing_write(
            envelope,
            current_identity=current,
            expected_source_digest=envelope.execution_identity["source_digest"],
            actor_cursor=-1,
            write_kind="terminal_result",
        )

    assert caught.value.code == MailboxV2ErrorCode.SCHEMA_INVALID
