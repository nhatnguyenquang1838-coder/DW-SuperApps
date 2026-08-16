"""External action fail-closed semantics (S3).

PRECHECK -> persist INTENT -> ACTION -> persist RESULT -> exact READBACK -> persist COMPARE.
Missing/mismatched readback must never return CONFIRMED.
Core stays SDK-agnostic; integrate only through the real active MVP adapter boundary.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


class ExternalActionState:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExternalActionRecord:
    run_id: str
    action_id: str
    state: str
    intent_payload: dict[str, Any] = field(default_factory=dict)
    result_payload: dict[str, Any] = field(default_factory=dict)
    readback_payload: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ExternalActionResult:
    action_id: str
    success: bool
    readback: dict[str, Any] | None = None
    evidence: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deterministic_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _readback_matches(intent: dict[str, Any], readback: dict[str, Any] | None) -> bool:
    if readback is None:
        return False
    return _deterministic_json(intent) == _deterministic_json(readback)


class ExternalActionLedger:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS external_actions (
                run_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                state TEXT NOT NULL,
                intent_payload TEXT DEFAULT '{}',
                result_payload TEXT DEFAULT '{}',
                readback_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, action_id)
            );
            CREATE INDEX IF NOT EXISTS idx_external_actions_run_id ON external_actions(run_id);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def record(self, run_id: str, action_id: str, intent_payload: dict[str, Any]) -> ExternalActionRecord:
        now = _now()
        try:
            self._conn.execute(
                """
                INSERT INTO external_actions (run_id, action_id, state, intent_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    action_id,
                    ExternalActionState.PENDING,
                    _deterministic_json(intent_payload),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"DUPLICATE_ACTION run_id={run_id} action_id={action_id}") from exc
        self._conn.commit()
        return ExternalActionRecord(
            run_id=run_id,
            action_id=action_id,
            state=ExternalActionState.PENDING,
            intent_payload=intent_payload,
            created_at=now,
            updated_at=now,
        )

    def finalize(self, run_id: str, action_id: str, result: ExternalActionResult) -> ExternalActionRecord:
        cursor = self._conn.execute(
            "SELECT * FROM external_actions WHERE run_id = ? AND action_id = ?",
            (run_id, action_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"ACTION_NOT_FOUND run_id={run_id} action_id={action_id}")

        if row["state"] != ExternalActionState.PENDING:
            raise ValueError(
                f"ACTION_NOT_PENDING run_id={run_id} action_id={action_id} state={row['state']}"
            )

        now = _now()
        readback = result.readback

        if not result.success:
            new_state = ExternalActionState.FAILED
        elif not _readback_matches(json.loads(row["intent_payload"]), readback):
            new_state = ExternalActionState.BLOCKED
        else:
            new_state = ExternalActionState.CONFIRMED

        self._conn.execute(
            """
            UPDATE external_actions
            SET state = ?, result_payload = ?, readback_payload = ?, updated_at = ?
            WHERE run_id = ? AND action_id = ?
            """,
            (
                new_state,
                _deterministic_json({"success": result.success, "evidence": result.evidence}),
                _deterministic_json(readback) if readback is not None else None,
                now,
                run_id,
                action_id,
            ),
        )
        self._conn.commit()

        return ExternalActionRecord(
            run_id=run_id,
            action_id=action_id,
            state=new_state,
            intent_payload=json.loads(row["intent_payload"]),
            result_payload={"success": result.success, "evidence": result.evidence},
            readback_payload=readback,
            created_at=row["created_at"],
            updated_at=now,
        )

    def load(self, run_id: str, action_id: str) -> ExternalActionRecord | None:
        cursor = self._conn.execute(
            "SELECT * FROM external_actions WHERE run_id = ? AND action_id = ?",
            (run_id, action_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ExternalActionRecord(
            run_id=row["run_id"],
            action_id=row["action_id"],
            state=row["state"],
            intent_payload=json.loads(row["intent_payload"]),
            result_payload=json.loads(row["result_payload"]),
            readback_payload=json.loads(row["readback_payload"]) if row["readback_payload"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def record_external_action(
    db_path: Path | str,
    run_id: str,
    action_id: str,
    intent_payload: dict[str, Any],
) -> ExternalActionRecord:
    ledger = ExternalActionLedger(db_path)
    try:
        return ledger.record(run_id, action_id, intent_payload)
    finally:
        ledger.close()


def finalize_external_action(
    db_path: Path | str,
    run_id: str,
    action_id: str,
    result: ExternalActionResult,
) -> ExternalActionRecord:
    ledger = ExternalActionLedger(db_path)
    try:
        return ledger.finalize(run_id, action_id, result)
    finally:
        ledger.close()


def load_external_action(
    db_path: Path | str,
    run_id: str,
    action_id: str,
) -> ExternalActionRecord | None:
    ledger = ExternalActionLedger(db_path)
    try:
        return ledger.load(run_id, action_id)
    finally:
        ledger.close()


def is_confirmed(db_path: Path | str, run_id: str, action_id: str) -> bool:
    rec = load_external_action(db_path, run_id, action_id)
    return rec is not None and rec.state == ExternalActionState.CONFIRMED
