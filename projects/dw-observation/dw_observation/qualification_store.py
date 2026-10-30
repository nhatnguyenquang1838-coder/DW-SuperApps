"""Idempotent qualification-receipt storage, isolated from DWO event history.

The LangGraph checkpointer must use a different database path. This module
never opens or mutates the canonical ``projection_events`` store.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import sqlite3
from functools import wraps
from threading import RLock
from typing import Callable, TypeVar

from .qualification_models import (
    DwoRunId,
    QualificationId,
    QualificationReceipt,
    subject_digest,
)


class QualificationReceiptConflict(RuntimeError):
    """The same qualification identity was presented with different content."""


_Result = TypeVar("_Result")


def _serialized(method: Callable[..., _Result]) -> Callable[..., _Result]:
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class SQLiteQualificationReceiptStore:
    """Small local/dev receipt store with read-only mode for projection consumers.

    Qualification receipts are immutable. Repeating the exact receipt is an
    idempotent success; attempting to reuse its qualification_id for different
    content is a fail-closed conflict.
    """

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path).resolve()
        self.read_only = read_only
        self._lock = RLock()
        if read_only:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            uri = self.path.as_uri() + "?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True, timeout=5, check_same_thread=False)
            self._connection.execute("PRAGMA query_only = ON")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=5, isolation_level=None, check_same_thread=False)
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS qualification_receipts (
                    qualification_id TEXT PRIMARY KEY,
                    receipt_id TEXT NOT NULL UNIQUE,
                    dwo_run_id TEXT NOT NULL,
                    task_ref TEXT,
                    subject_digest TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_qualification_receipts_run "
                "ON qualification_receipts (dwo_run_id, subject_digest)"
            )

    def __enter__(self) -> "SQLiteQualificationReceiptStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    @_serialized
    def close(self) -> None:
        self._connection.close()

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise PermissionError("read-only qualification receipt store cannot write")

    @staticmethod
    def _payload(receipt: QualificationReceipt) -> str:
        return json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @_serialized
    def put_idempotent(self, receipt: QualificationReceipt) -> QualificationReceipt:
        """Persist exactly one immutable receipt per qualification identity."""
        self._ensure_writable()
        payload = self._payload(receipt)
        qid = receipt.qualification_id.value
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._connection.execute(
                "SELECT payload_json FROM qualification_receipts WHERE qualification_id = ?",
                (qid,),
            ).fetchone()
            if existing is not None:
                if existing[0] != payload:
                    raise QualificationReceiptConflict(
                        f"qualification_id {qid!r} already has a different immutable receipt"
                    )
                self._connection.execute("COMMIT")
                return QualificationReceipt.from_dict(json.loads(existing[0]))

            task_ref = receipt.subject.task_ref.value if receipt.subject.task_ref is not None else None
            self._connection.execute(
                """INSERT INTO qualification_receipts
                   (qualification_id, receipt_id, dwo_run_id, task_ref, subject_digest, receipt_digest, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    qid,
                    receipt.receipt_id,
                    receipt.subject.dwo_run_id.value,
                    task_ref,
                    receipt.subject_digest,
                    receipt.receipt_digest,
                    payload,
                ),
            )
            self._connection.execute("COMMIT")
            return receipt
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    @_serialized
    def get(self, qualification_id: QualificationId | str) -> QualificationReceipt | None:
        qid = qualification_id.value if isinstance(qualification_id, QualificationId) else qualification_id
        row = self._connection.execute(
            "SELECT payload_json FROM qualification_receipts WHERE qualification_id = ?",
            (qid,),
        ).fetchone()
        if row is None:
            return None
        return QualificationReceipt.from_dict(json.loads(row[0]))

    @_serialized
    def get_for_run(
        self,
        dwo_run_id: DwoRunId | str,
        *,
        expected_subject_digest: str | None = None,
    ) -> tuple[QualificationReceipt, ...]:
        run_id = dwo_run_id.value if isinstance(dwo_run_id, DwoRunId) else dwo_run_id
        if expected_subject_digest is None:
            rows = self._connection.execute(
                "SELECT payload_json FROM qualification_receipts WHERE dwo_run_id = ? ORDER BY qualification_id",
                (run_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """SELECT payload_json FROM qualification_receipts
                   WHERE dwo_run_id = ? AND subject_digest = ? ORDER BY qualification_id""",
                (run_id, expected_subject_digest),
            ).fetchall()
        return tuple(QualificationReceipt.from_dict(json.loads(row[0])) for row in rows)

    @_serialized
    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM qualification_receipts").fetchone()
        return int(row[0])


def assert_storage_isolation(
    checkpoint_path: str | Path,
    receipt_path: str | Path,
    projection_events_path: str | Path,
) -> None:
    """Refuse a topology that co-locates operational/receipt/event databases."""
    names = {
        "LangGraph checkpoint": Path(checkpoint_path).resolve(),
        "qualification receipt": Path(receipt_path).resolve(),
        "canonical projection_events": Path(projection_events_path).resolve(),
    }
    items = list(names.items())
    for index, (left_name, left_path) in enumerate(items):
        for right_name, right_path in items[index + 1 :]:
            if os.path.normcase(str(left_path)) == os.path.normcase(str(right_path)):
                raise ValueError(f"{left_name} and {right_name} stores must be physically separate")
