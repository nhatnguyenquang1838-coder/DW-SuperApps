"""One-shot Controller recovery does not write mailbox execution authority."""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

from scripts import taskcontroller_mailbox_recover as cli

HEAD = "f6fd4121e492b61e8e0781614cd4b627d99ad979"
RUN = "scrum781-q0-20260920T074727Z"


def _args(sha=HEAD):
    return argparse.Namespace(repository="nhatnguyenquang1838-coder/gwc", issue=575,
                              run_id=RUN, expected_head_sha=sha, token_env="GITHUB_TOKEN")


class Checkpoint:
    def __init__(self, phase="WAIT_EXECUTOR", next_action="AWAIT_EXECUTOR_EVENT", sha=HEAD):
        self.phase, self.next_action, self.exact_head_sha = phase, next_action, sha

    def to_dict(self):
        return dict(phase=self.phase, next_action=self.next_action, exact_head_sha=self.exact_head_sha)

    def __eq__(self, other):
        return isinstance(other, Checkpoint) and self.to_dict() == other.to_dict()


def harness(monkeypatch, *, before=None, after=None):
    monkeypatch.setenv("GITHUB_TOKEN", "unit-test-token")
    before = before or Checkpoint()
    after = after or Checkpoint("WAIT_CONTROLLER", "RESOLVE_EXECUTION_AUTHORITY")
    counts = dict(read=0, recover=0, receipt=0)

    class Store:
        def __init__(self, transport, repository, issue_number):
            assert repository == "nhatnguyenquang1838-coder/gwc" and issue_number == 575

        def latest_receipt(self, run_id, kind):
            counts["receipt"] += 1
            assert run_id == RUN and kind == "dw.taskcontroller.continuation/v1"
            return SimpleNamespace(to_dict=lambda: {"comment_ref": "github://example/issuecomment-123"})

    def readback(store, run_id):
        counts["read"] += 1
        assert run_id == RUN
        return before if counts["read"] == 1 else after

    def runtime_recover(**kwargs):
        counts["recover"] += 1
        assert kwargs["run_id"] == RUN and kwargs["observed_at"] == "2026-10-10T00:00:00+00:00"
        return SimpleNamespace(checkpoint=after,
                               controller_cursor=SimpleNamespace(to_dict=lambda: {"last_event_seq": 2}))

    monkeypatch.setattr(cli, "GitHubRestIssueCommentTransport", lambda token: token)
    monkeypatch.setattr(cli, "GitHubContinuationStore", Store)
    monkeypatch.setattr(cli, "GitHubMailboxRepository", lambda transport: transport)
    monkeypatch.setattr(cli, "recover_continuation", readback)
    monkeypatch.setattr(cli, "recover_high_integrity_session", runtime_recover)
    return counts


def test_recovery_continuation_verified_without_execution_grant(monkeypatch):
    counts = harness(monkeypatch)
    x = cli.recover_once(_args(), observed_at="2026-10-10T00:00:00+00:00")
    assert counts == {"read": 2, "recover": 1, "receipt": 1}
    assert x["status"] == "RECOVERY_CONTINUATION_VERIFIED"
    assert x["checkpoint"]["next_action"] == "RESOLVE_EXECUTION_AUTHORITY"
    assert not x["authority_granted"]
    assert not x["executor_wakeup_allowed"]
    assert not x["protected_effects_allowed"]
    assert not x["mailbox_event_created"]
    assert x["controller_cursor"]["last_event_seq"] == 2


def test_head_mismatch_fails_before_state_mutation(monkeypatch):
    counts = harness(monkeypatch, before=Checkpoint(sha="a" * 40))
    with pytest.raises(ValueError, match="RECOVERY_HEAD_MISMATCH"):
        cli.recover_once(_args(), observed_at="2026-10-10T00:00:00+00:00")
    assert counts["recover"] == 0


def test_illegal_continuation_phase_fails_before_state_mutation(monkeypatch):
    counts = harness(monkeypatch, before=Checkpoint(phase="TERMINAL"))
    with pytest.raises(ValueError, match="RECOVERY_PHASE_INVALID"):
        cli.recover_once(_args(), observed_at="2026-10-10T00:00:00+00:00")
    assert counts["recover"] == 0


def test_unexpired_execution_attempt_cannot_be_released(monkeypatch):
    counts = harness(monkeypatch, after=Checkpoint())
    with pytest.raises(ValueError, match="RECOVERY_BOUNDARY_NOT_REACHED"):
        cli.recover_once(_args(), observed_at="2026-10-10T00:00:00+00:00")
    assert counts["recover"] == 1


def test_missing_token_cannot_call_runtime(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GITHUB_TOKEN is required"):
        cli.recover_once(_args(), observed_at="2026-10-10T00:00:00+00:00")


def test_invalid_head_cannot_call_runtime():
    with pytest.raises(ValueError, match="expected-head-sha"):
        cli.recover_once(_args("not-a-sha"))
