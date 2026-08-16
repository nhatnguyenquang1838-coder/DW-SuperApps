"""RED tests for SQLite Run Ledger (S2)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.sqlite_writer import SQLiteRunLedger
from taskcontroller.audit.manifest import RunManifest
from taskcontroller.audit.summary import RunSummary
from taskcontroller.audit.query import RunQuery


def _make_event(run_id: str, sequence: int, decision_kind: str = "TEST") -> AuditEvent:
    return AuditEvent(
        event_id=f"evt-{run_id}-{sequence}",
        timestamp="2026-08-16T00:00:00Z",
        run_id=run_id,
        source="test",
        decision_kind=decision_kind,
        payload_summary=f"event {sequence}",
        before={},
        after={},
    )


class TestSQLiteRunLedgerCreation:
    def test_creates_database_file(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        SQLiteRunLedger(db)
        assert db.exists()

    def test_creates_expected_tables(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        SQLiteRunLedger(db)
        with sqlite3.connect(db) as conn:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "runs" in tables
        assert "events" in tables
        assert "manifests" in tables
        assert "run_summaries" in tables


class TestSQLiteRunLedgerAppend:
    def test_append_returns_sequence(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        seq = ledger.append("run-1", _make_event("run-1", 1))
        assert seq == 1

    def test_append_increments_sequence(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        ledger.append("run-1", _make_event("run-1", 1))
        seq = ledger.append("run-1", _make_event("run-1", 2))
        assert seq == 2

    def test_duplicate_rejected(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        ledger.append("run-1", _make_event("run-1", 1))
        with pytest.raises(ValueError, match="DUPLICATE_EVENT"):
            ledger.append("run-1", _make_event("run-1", 1))

    def test_different_runs_independent_sequences(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        assert ledger.append("run-a", _make_event("run-a", 1)) == 1
        assert ledger.append("run-b", _make_event("run-b", 1)) == 1


class TestSQLiteRunLedgerReopen:
    def test_reopen_and_append(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        ledger1 = SQLiteRunLedger(db)
        ledger1.append("run-1", _make_event("run-1", 1))
        ledger2 = SQLiteRunLedger(db)
        seq = ledger2.append("run-1", _make_event("run-1", 2))
        assert seq == 2

    def test_reconstruct_events(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        ledger1 = SQLiteRunLedger(db)
        ledger1.append("run-1", _make_event("run-1", 1))
        ledger1.append("run-1", _make_event("run-1", 2))
        ledger2 = SQLiteRunLedger(db)
        events = ledger2.events("run-1")
        assert [e.event_id for e in events] == ["evt-run-1-1", "evt-run-1-2"]


class TestSQLiteRunLedgerManifest:
    def test_upsert_manifest(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        manifest = RunManifest(
            run_id="run-1",
            schema_version="1.0",
            created_at="2026-08-16T00:00:00Z",
            updated_at="2026-08-16T00:00:00Z",
            metadata={"author": "test"},
        )
        ledger.upsert_manifest(manifest)
        loaded = ledger.manifest("run-1")
        assert loaded.run_id == "run-1"
        assert loaded.schema_version == "1.0"
        assert loaded.metadata["author"] == "test"

    def test_missing_manifest_returns_none(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        assert ledger.manifest("missing") is None


class TestSQLiteRunLedgerSummary:
    def test_write_and_read_summary(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        summary = RunSummary(
            run_id="run-1",
            first_sequence=1,
            last_sequence=2,
            event_count=2,
            first_event_id="evt-run-1-1",
            last_event_id="evt-run-1-2",
            closed_at="2026-08-16T00:01:00Z",
        )
        ledger.upsert_summary(summary)
        loaded = ledger.summary("run-1")
        assert loaded is not None
        assert loaded.event_count == 2
        assert loaded.last_event_id == "evt-run-1-2"

    def test_missing_summary_returns_none(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        assert ledger.summary("missing") is None


class TestSQLiteRunLedgerQuery:
    def test_query_by_decision_kind(self, tmp_path: Path) -> None:
        ledger = SQLiteRunLedger(tmp_path / "ledger.db")
        ledger.append("run-1", _make_event("run-1", 1, "A"))
        ledger.append("run-1", _make_event("run-1", 2, "B"))
        results = ledger.query(run_id="run-1", decision_kind="A")
        assert len(results) == 1
        assert results[0].decision_kind == "A"

    def test_query_after_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        SQLiteRunLedger(db).append("run-1", _make_event("run-1", 1, "A"))
        results = SQLiteRunLedger(db).query(run_id="run-1")
        assert len(results) == 1


class TestDeterministicSerialization:
    def test_event_json_is_deterministic(self) -> None:
        event = AuditEvent(
            event_id="evt-1",
            timestamp="2026-08-16T00:00:00Z",
            run_id="run-1",
            source="test",
            decision_kind="TEST",
            payload_summary="payload",
            before={"b": 2, "a": 1},
            after={"b": 2, "a": 1},
        )
        first = event.to_json()
        second = event.to_json()
        assert first == second
        parsed = json.loads(first)
        assert parsed["before"] == {"a": 1, "b": 2}
        assert parsed["after"] == {"a": 1, "b": 2}
