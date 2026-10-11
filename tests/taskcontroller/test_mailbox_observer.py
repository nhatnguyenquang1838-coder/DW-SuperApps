"""Read-only, exact-ref MAILBOX_OBSERVER contract; no canonical cursor writes."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from taskcontroller.controlplane.orchestration_policy import (
    HOLD_EFFECT,
    HOLD_RUN,
    decide_executor_loop_continuity,
)
from taskcontroller.interaction.continuation import ControllerContinuation
from taskcontroller.interaction.mailbox_repository import (
    InMemoryMailboxRepository,
    MailboxActorCursor,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
RUN = "test-scrum781-observer-run"
NODE = "node-1"
MAILBOX_REF = "github://example/gwc/issues/1#test-scrum781-observer-controller-v2"
AGENT_INSTANCE = "hermes-desktop-instance-1"


def _observer_decision(**overrides: Any):
    args: dict[str, Any] = {
        "loop_role": "MAILBOX_OBSERVER",
        "loop_run_id": RUN,
        "canonical_run_id": RUN,
        "execute_contract_current": False,
        "mailbox_observer_qualified": True,
        "awaiting_controller_event": True,
    }
    args.update(overrides)
    return decide_executor_loop_continuity(**args)


def _continuation(**updates):
    values = {
        "run_id": RUN,
        "controller_epoch": 1,
        "phase": "WAIT_EXECUTOR",
        "status": "ACTIVE",
        "next_action": "AWAIT_EXECUTOR_EVENT",
        "controller_mailbox_ref": MAILBOX_REF,
        "controller_seq": 1,
        "executor_actor": "hermes-desktop",
        "executor_mailbox_ref": "github://example/gwc/issues/1#test-scrum781-observer-executor-v2",
        "expected_executor_seq": 1,
        "last_seen_executor_seq": 0,
        "wakeup_binding": "hermes-desktop-local-ipc",
        "exact_head_sha": "a" * 40,
        "updated_at": "2026-10-12T00:00:00Z",
    }
    values.update(updates)
    return ControllerContinuation(**values)


def _controller_event(*, seq: int, agent_instance: str = AGENT_INSTANCE, run_id: str = RUN):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = copy.deepcopy(fixture["cases"]["execution_request"])
    payload.update(
        run_id=run_id,
        node_id=NODE,
        seq=seq,
        message_id=f"message-{run_id}-{seq}",
        idempotency_key=f"idem-{run_id}-{seq}",
        producer={"namespace": "controller", "actor_id": "controller-1", "role": "controller"},
        recipient={"agent_instance": agent_instance, "capability": "taskcontroller.executor"},
    )
    payload["attempt"]["agent_instance"] = agent_instance
    payload["attempt"]["attempt_id"] = f"attempt-{run_id}-{seq}"
    payload["execution_identity"].update(
        run_id=run_id,
        node_id=NODE,
        attempt_id=f"attempt-{run_id}-{seq}",
    )
    payload["provenance"]["agent_instance"] = "controller-1"
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _cursor():
    return MailboxActorCursor.initial(
        MAILBOX_REF, run_id=RUN, node_id=NODE, actor_namespace="controller"
    )


def test_observer_exact_reads_new_controller_event_without_acknowledging_cursor():
    from taskcontroller.interaction.mailbox_observer import observe_controller_mailbox

    repository = InMemoryMailboxRepository()
    repository.write(MAILBOX_REF, -1, _controller_event(seq=2))
    cursor = _cursor()

    events, observed_cursor = observe_controller_mailbox(
        repository=repository,
        continuation=_continuation(),
        observer_cursor=cursor,
        node_id=NODE,
        agent_instance=AGENT_INSTANCE,
        continuity_decision=_observer_decision(),
        max_events=8,
    )

    assert len(events) == 1
    assert events[0].event_id == f"{MAILBOX_REF}:event-0"
    assert observed_cursor.last_event_seq == 0
    assert observed_cursor.last_event_digest == events[0].event_digest
    assert repository.read_cursor(
        MAILBOX_REF, RUN, NODE, "controller"
    ).last_event_seq == -1  # observation is not canonical command consumption


def test_no_new_event_returns_same_observed_cursor_and_no_candidate():
    from taskcontroller.interaction.mailbox_observer import observe_controller_mailbox

    repository = InMemoryMailboxRepository()
    cursor = _cursor()
    events, observed_cursor = observe_controller_mailbox(
        repository=repository,
        continuation=_continuation(),
        observer_cursor=cursor,
        node_id=NODE,
        agent_instance=AGENT_INSTANCE,
        continuity_decision=_observer_decision(),
        max_events=8,
    )

    assert events == ()
    assert observed_cursor == cursor


@pytest.mark.parametrize("hold_type,user_paused", [(HOLD_RUN, False), (None, True)])
def test_run_hold_or_user_pause_suppresses_read_and_does_not_advance_cursor(hold_type, user_paused):
    from taskcontroller.interaction.mailbox_observer import observe_controller_mailbox

    repository = InMemoryMailboxRepository()
    repository.write(MAILBOX_REF, -1, _controller_event(seq=2))
    cursor = _cursor()

    events, observed_cursor = observe_controller_mailbox(
        repository=repository,
        continuation=_continuation(),
        observer_cursor=cursor,
        node_id=NODE,
        agent_instance=AGENT_INSTANCE,
        continuity_decision=_observer_decision(hold_type=hold_type, user_paused=user_paused),
        max_events=8,
    )

    assert events == ()
    assert observed_cursor == cursor


def test_effect_hold_allows_read_only_observation_without_effect_authority():
    from taskcontroller.interaction.mailbox_observer import observe_controller_mailbox

    repository = InMemoryMailboxRepository()
    repository.write(MAILBOX_REF, -1, _controller_event(seq=2))
    events, observed_cursor = observe_controller_mailbox(
        repository=repository,
        continuation=_continuation(),
        observer_cursor=_cursor(),
        node_id=NODE,
        agent_instance=AGENT_INSTANCE,
        continuity_decision=_observer_decision(hold_type=HOLD_EFFECT),
        max_events=8,
    )

    assert len(events) == 1
    assert observed_cursor.last_event_seq == 0


def test_unqualified_observer_and_binding_mismatch_never_scan():
    from taskcontroller.interaction.mailbox_observer import observe_controller_mailbox

    repository = InMemoryMailboxRepository()
    cursor = _cursor()
    with pytest.raises(ValueError, match="observer"):
        observe_controller_mailbox(
            repository=repository,
            continuation=_continuation(),
            observer_cursor=cursor,
            node_id=NODE,
            agent_instance=AGENT_INSTANCE,
            continuity_decision=_observer_decision(mailbox_observer_qualified=False),
            max_events=8,
        )
    with pytest.raises(ValueError, match="binding"):
        observe_controller_mailbox(
            repository=repository,
            continuation=_continuation(run_id="other-run"),
            observer_cursor=cursor,
            node_id=NODE,
            agent_instance=AGENT_INSTANCE,
            continuity_decision=_observer_decision(),
            max_events=8,
        )


def test_observer_is_bounded_and_does_not_skip_unprocessed_events():
    from taskcontroller.interaction.mailbox_observer import observe_controller_mailbox

    repository = InMemoryMailboxRepository()
    repository.write(MAILBOX_REF, -1, _controller_event(seq=2))
    repository.write(MAILBOX_REF, 0, _controller_event(seq=3))
    first, cursor = observe_controller_mailbox(
        repository=repository,
        continuation=_continuation(),
        observer_cursor=_cursor(),
        node_id=NODE,
        agent_instance=AGENT_INSTANCE,
        continuity_decision=_observer_decision(),
        max_events=1,
    )
    second, final_cursor = observe_controller_mailbox(
        repository=repository,
        continuation=_continuation(),
        observer_cursor=cursor,
        node_id=NODE,
        agent_instance=AGENT_INSTANCE,
        continuity_decision=_observer_decision(),
        max_events=1,
    )

    assert [event.logical_seq for event in first] == [2]
    assert [event.logical_seq for event in second] == [3]
    assert final_cursor.last_event_seq == 1
    assert repository.read_cursor(MAILBOX_REF, RUN, NODE, "controller").last_event_seq == -1
