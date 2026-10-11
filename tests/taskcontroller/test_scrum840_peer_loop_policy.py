"""SCRUM-840 peer collaboration and opt-in Loop mailbox observation contracts.

Pure decisions only: neither a peer agreement nor a poll creates a lease, a
mailbox event or permission to resume a protected effect.
"""
import pytest

from taskcontroller.controlplane.orchestration_policy import (
    HOLD_EFFECT,
    HOLD_RUN,
    OrchestrationPolicyError,
    decide_executor_loop_continuity,
    decide_peer_collaboration,
)


def _peer(**overrides):
    args = dict(
        actor_a="gpt-agent",
        actor_b="hermes-agent",
        proposal_digest_a="sha256:" + "a" * 64,
        proposal_digest_b="sha256:" + "a" * 64,
        scope_current=True,
        existing_effect_authority=True,
        discussion_round=1,
        max_rounds=4,
    )
    args.update(overrides)
    return decide_peer_collaboration(**args)


def _observer(**overrides):
    args = dict(
        loop_role="MAILBOX_OBSERVER",
        loop_run_id="scrum781-q0-fresh-20261010-r1",
        canonical_run_id="scrum781-q0-fresh-20261010-r1",
        execute_contract_current=False,
        mailbox_observer_qualified=True,
        awaiting_controller_event=True,
    )
    args.update(overrides)
    return decide_executor_loop_continuity(**args)


def test_peer_equal_rights_and_shared_decision_is_not_new_grant():
    first = _peer()
    reverse = _peer(actor_a="hermes-agent", actor_b="gpt-agent")
    assert first.status == reverse.status == "AGREED"
    assert first.typed_next == reverse.typed_next == "CONTINUE_WITH_EXISTING_AUTHORITY"
    assert not first.authority_granted and not reverse.authority_granted
    assert not first.requires_human


def test_peers_continue_discussion_without_waiting_for_higher_rank():
    pending = _peer(proposal_digest_b=None)
    disagreed = _peer(proposal_digest_b="sha256:" + "b" * 64)
    assert pending.status == "DISCUSS"
    assert disagreed.status == "DISCUSS"
    assert pending.typed_next == disagreed.typed_next == "CONTINUE_PEER_DISCUSSION"


def test_round_budget_escalates_disagreement_to_human_only_when_unresolved():
    result = _peer(proposal_digest_b="sha256:" + "b" * 64, discussion_round=4)
    assert result.status == "NEEDS_HUMAN_DECISION"
    assert result.requires_human
    assert not result.authority_granted


@pytest.mark.parametrize("kwargs", [
    {"scope_current": False},
    {"existing_effect_authority": False},
])
def test_peer_consensus_never_expands_scope_or_issues_effect_authority(kwargs):
    decision = _peer(**kwargs)
    assert decision.status == "AUTHORITY_BOUNDARY"
    assert decision.typed_next == "REQUEST_BOUNDED_AUTHORITY"
    assert not decision.authority_granted


@pytest.mark.parametrize("kwargs", [
    {"user_paused": True},
    {"run_hold": True},
])
def test_peer_consensus_cannot_bypass_pause_or_run_hold(kwargs):
    decision = _peer(**kwargs)
    assert decision.status == "PAUSED"
    assert not decision.authority_granted


@pytest.mark.parametrize("kwargs", [
    {"actor_b": "gpt-agent"},
    {"proposal_digest_a": "not-sha"},
    {"discussion_round": 5},
    {"scope_current": "yes"},
])
def test_peer_collaboration_rejects_bad_binding(kwargs):
    with pytest.raises(OrchestrationPolicyError):
        _peer(**kwargs)


def test_qualified_mailbox_observer_can_read_cursor_without_execute_grant():
    d = _observer()
    assert d.scheduler_action == "ALLOW_READ_ONLY_MAILBOX_OBSERVATION"
    assert d.typed_next == "OBSERVE_MAILBOX_CURSOR"
    assert d.executor_session_action == "AWAIT_NEW_MAILBOX_EVENT"
    assert not d.effects_allowed and not d.auto_resume_allowed


def test_new_event_requires_exact_readback_not_automatic_execution():
    d = _observer(newer_event_observed=True, execute_contract_current=True)
    assert d.typed_next == "EXACT_READ_NEW_CONTROLLER_EVENT"
    assert not d.effects_allowed and not d.auto_resume_allowed


def test_missing_observer_qualification_cannot_poll():
    d = _observer(mailbox_observer_qualified=False)
    assert d.scheduler_action == "PAUSE_UNQUALIFIED_MAILBOX_OBSERVER"
    assert d.typed_next == "QUALIFY_MAILBOX_OBSERVER"


def test_legacy_mailbox_poll_role_remains_disabled():
    d = _observer(loop_role="MAILBOX_POLL")
    assert d.scheduler_action == "PAUSE_MAILBOX_POLL_SCHEDULER"
    assert d.effects_allowed is False


def test_qualified_observer_may_check_cursor_during_effect_hold():
    d = _observer(hold_type=HOLD_EFFECT)
    assert d.scheduler_action == "ALLOW_READ_ONLY_MAILBOX_OBSERVATION"
    assert not d.effects_allowed


@pytest.mark.parametrize("kwargs, next_action", [
    ({"user_paused": True}, "RESOLVE_USER_PAUSE"),
    ({"hold_type": HOLD_RUN}, "RESOLVE_RUN_HOLD"),
    ({"loop_run_id": "obsolete-run"}, "RESOLVE_RUN_BINDING"),
])
def test_loop_observer_cannot_override_holds_or_wrong_run(kwargs, next_action):
    d = _observer(**kwargs)
    assert d.typed_next == next_action
    assert not d.effects_allowed
    assert d.scheduler_action != "ALLOW_READ_ONLY_MAILBOX_OBSERVATION"


def test_invalid_observer_flag_fails_closed():
    with pytest.raises(OrchestrationPolicyError, match="LOOP_CONTRACT_INVALID"):
        _observer(mailbox_observer_qualified="yes")
