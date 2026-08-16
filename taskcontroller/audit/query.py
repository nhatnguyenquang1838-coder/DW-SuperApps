"""Query helpers for SQLite Run Ledger."""
from __future__ import annotations

from typing import Any

from taskcontroller.audit.sqlite_writer import SQLiteRunLedger
from taskcontroller.audit.event import AuditEvent


class RunQuery:
    def __init__(self, ledger: SQLiteRunLedger) -> None:
        self._ledger = ledger

    def by_decision_kind(self, decision_kind: str) -> list[AuditEvent]:
        return self._ledger.query(run_id="*", decision_kind=decision_kind)

    def by_run_id(self, run_id: str) -> list[AuditEvent]:
        return self._ledger.query(run_id=run_id)


def find_runs(ledger: SQLiteRunLedger, decision_kind: str | None = None) -> list[str]:
    sql = "SELECT DISTINCT run_id FROM events"
    params: list[Any] = []
    if decision_kind is not None:
        sql += " WHERE decision_kind = ?"
        params.append(decision_kind)
    sql += " ORDER BY run_id"
    cursor = ledger._conn.execute(sql, params)
    return [row[0] for row in cursor.fetchall()]
