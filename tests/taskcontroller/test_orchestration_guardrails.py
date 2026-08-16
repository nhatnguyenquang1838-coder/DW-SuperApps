import pytest
from unittest.mock import MagicMock

from taskcontroller.orchestration import GuardrailChain, external_action_pattern
from taskcontroller.audit.guardrails import GuardrailResult
from taskcontroller.audit.facade import NoOpAuditFacade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chain(
    audit: NoOpAuditFacade | None = None,
    run_id: str = "run-1",
    now_str: str = "2026-08-16T10:00:00",
) -> GuardrailChain:
    audit = audit or NoOpAuditFacade()
    return GuardrailChain(audit, run_id, lambda: now_str)


# ---------------------------------------------------------------------------
# GuardrailChain.run() — guardrail block scenarios
# ---------------------------------------------------------------------------

class TestGuardrailChainRun:
    """GuardrailChain.run() fail-closed: first blocked guardrail stops the chain."""

    def test_terminal_blocked(self) -> None:
        chain = _make_chain()
        r = chain.run(run_status="COMPLETED")
        assert r.blocked is True
        assert r.reason == "run_terminal"

    def test_duplicate_root_blocked(self) -> None:
        chain = _make_chain()
        r = chain.run(
            binding_key="jira",
            existing_root="root.A",
            proposed_root="root.B",
        )
        assert r.blocked is True
        assert r.reason == "duplicate_root"

    def test_authority_mismatch_blocked(self) -> None:
        chain = _make_chain()
        r = chain.run(
            authority_ref="auth-1",
            expected_authority="auth-2",
        )
        assert r.blocked is True
        assert r.reason == "authority_mismatch"

    def test_invalid_sha_blocked(self) -> None:
        chain = _make_chain()
        r = chain.run(
            head_sha="g" * 40,
            action_kind="jira",
        )
        assert r.blocked is True
        assert "invalid" in r.reason

    def test_all_pass_returns_unblocked(self) -> None:
        chain = _make_chain()
        r = chain.run(
            run_status="RUNNING",
            binding_key="jira",
            existing_root="root.A",
            proposed_root="root.A",
            authority_ref="auth-1",
            expected_authority="auth-1",
            head_sha="a" * 40,
            action_kind="jira",
        )
        assert r.blocked is False
        assert r.reason == ""

    def test_no_checks_when_args_empty(self) -> None:
        chain = _make_chain()
        r = chain.run()
        assert r.blocked is False

    def test_terminal_check_runs_first(self) -> None:
        """When terminal and duplicate_root both block, terminal wins (first in chain)."""
        chain = _make_chain()
        r = chain.run(
            run_status="COMPLETED",
            binding_key="jira",
            existing_root="root.A",
            proposed_root="root.B",
        )
        assert r.blocked is True
        assert r.reason == "run_terminal"

    def test_emits_audit_event_on_block(self) -> None:
        audit = MagicMock()
        chain = GuardrailChain(audit, "run-1", lambda: "2026-08-16T10:00:00")
        chain.run(run_status="COMPLETED")
        assert audit.emit.call_count == 1
        event = audit.emit.call_args[0][0]
        assert event.decision_kind == "GUARDRAIL_BLOCKED"
        assert event.source == "guardrail.chain"
        assert event.run_id == "run-1"


# ---------------------------------------------------------------------------
# external_action_pattern()
# ---------------------------------------------------------------------------

class TestExternalActionPattern:
    """external_action_pattern: pre-check → external_call → readback → compare."""

    def test_pre_check_blocked_returns_rejected(self) -> None:
        audit = NoOpAuditFacade()
        result = external_action_pattern(
            audit=audit,
            run_id="run-1",
            run_status="COMPLETED",
            action_kind="jira",
            authority_ref="auth-1",
            expected_authority="auth-1",
            head_sha="a" * 40,
            existing_root=None,
            proposed_root="root.A",
            now=lambda: "2026-08-16T10:00:00",
            external_call=lambda: {"id": "123"},
            readback=lambda after: {"exact_match": True},
        )
        assert result["accepted"] is False
        assert result["reason"] == "run_terminal"

    def test_full_success_path(self) -> None:
        audit = NoOpAuditFacade()
        external_result = {"id": "123", "status": "DONE"}

        def external_call() -> dict:
            return external_result

        def readback(after: dict) -> dict:
            return {"exact_match": True, "after": after}

        result = external_action_pattern(
            audit=audit,
            run_id="run-1",
            run_status="RUNNING",
            action_kind="jira",
            authority_ref="auth-1",
            expected_authority="auth-1",
            head_sha="a" * 40,
            existing_root=None,
            proposed_root="root.A",
            now=lambda: "2026-08-16T10:00:00",
            external_call=external_call,
            readback=readback,
        )
        assert result["accepted"] is True
        assert result["result"] == external_result

    def test_readback_mismatch_returns_rejected(self) -> None:
        audit = NoOpAuditFacade()

        def external_call() -> dict:
            return {"id": "123"}

        def readback(after: dict) -> dict:
            return {"exact_match": False, "mismatch": "expected X got Y"}

        result = external_action_pattern(
            audit=audit,
            run_id="run-1",
            run_status="RUNNING",
            action_kind="jira",
            authority_ref="auth-1",
            expected_authority="auth-1",
            head_sha="a" * 40,
            existing_root=None,
            proposed_root="root.A",
            now=lambda: "2026-08-16T10:00:00",
            external_call=external_call,
            readback=readback,
        )
        assert result["accepted"] is False
        assert result["reason"] == "readback_mismatch"
