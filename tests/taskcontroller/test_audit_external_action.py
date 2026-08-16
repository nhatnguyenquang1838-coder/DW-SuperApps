"""RED tests for external action fail-closed semantics (S3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.external_action import (
    ExternalActionRecord,
    ExternalActionResult,
    ExternalActionState,
    record_external_action,
    finalize_external_action,
    load_external_action,
    is_confirmed,
)


class TestExternalActionStateMachine:
    def test_record_returns_pending(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        rec = record_external_action(db, "run-1", "ACTION-1", {"url": "https://example.com"})
        assert rec.state == ExternalActionState.PENDING
        assert rec.run_id == "run-1"
        assert rec.action_id == "ACTION-1"

    def test_finalize_pending_returns_confirmed(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        intent = {"url": "https://example.com"}
        record_external_action(db, "run-1", "ACTION-1", intent)
        result = ExternalActionResult(
            action_id="ACTION-1",
            success=True,
            readback=intent,
            evidence=["ts-123"],
        )
        rec = finalize_external_action(db, "run-1", "ACTION-1", result)
        assert rec.state == ExternalActionState.CONFIRMED

    def test_finalize_failed_returns_failed(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        record_external_action(db, "run-1", "ACTION-1", {})
        result = ExternalActionResult(
            action_id="ACTION-1",
            success=False,
            readback={"error": "timeout"},
            evidence=[],
        )
        rec = finalize_external_action(db, "run-1", "ACTION-1", result)
        assert rec.state == ExternalActionState.FAILED

    def test_missing_readback_never_confirmed(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        record_external_action(db, "run-1", "ACTION-1", {})
        result = ExternalActionResult(
            action_id="ACTION-1",
            success=True,
            readback=None,
            evidence=[],
        )
        rec = finalize_external_action(db, "run-1", "ACTION-1", result)
        assert rec.state == ExternalActionState.BLOCKED
        assert is_confirmed(db, "run-1", "ACTION-1") is False

    def test_mismatched_readback_never_confirmed(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        record_external_action(db, "run-1", "ACTION-1", {"expected": "ok"})
        result = ExternalActionResult(
            action_id="ACTION-1",
            success=True,
            readback={"status": "MISMATCH"},
            evidence=[],
        )
        rec = finalize_external_action(db, "run-1", "ACTION-1", result)
        assert rec.state == ExternalActionState.BLOCKED
        assert is_confirmed(db, "run-1", "ACTION-1") is False

    def test_duplicate_action_id_rejected(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        record_external_action(db, "run-1", "ACTION-1", {})
        with pytest.raises(ValueError, match="DUPLICATE_ACTION"):
            record_external_action(db, "run-1", "ACTION-1", {})

    def test_reopen_and_finalize(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        intent = {"status": "ok"}
        record_external_action(db, "run-1", "ACTION-1", intent)
        # reopen
        rec = load_external_action(db, "run-1", "ACTION-1")
        assert rec.state == ExternalActionState.PENDING
        result = ExternalActionResult(
            action_id="ACTION-1",
            success=True,
            readback=intent,
            evidence=["ts-456"],
        )
        finalize_external_action(db, "run-1", "ACTION-1", result)
        # reopen again
        rec2 = load_external_action(db, "run-1", "ACTION-1")
        assert rec2.state == ExternalActionState.CONFIRMED

    def test_missing_action_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        assert load_external_action(db, "run-1", "MISSING") is None

    def test_multiple_runs_independent(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        record_external_action(db, "run-a", "ACTION-1", {})
        record_external_action(db, "run-b", "ACTION-1", {})
        assert load_external_action(db, "run-a", "ACTION-1").run_id == "run-a"
        assert load_external_action(db, "run-b", "ACTION-1").run_id == "run-b"
