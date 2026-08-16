"""SQLite Run Ledger — ordered append-only audit events."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.manifest import RunManifest
from taskcontroller.audit.summary import RunSummary


SCHEMA_VERSION = "1.0"


class SQLiteRunLedger:
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

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                decision_kind TEXT NOT NULL,
                node_id TEXT DEFAULT '',
                actor TEXT DEFAULT '',
                authority_ref TEXT DEFAULT '',
                payload_summary TEXT DEFAULT '',
                raw_payload_ref TEXT DEFAULT '',
                before TEXT DEFAULT '{}',
                after TEXT DEFAULT '{}',
                evidence_refs TEXT DEFAULT '[]',
                annotations TEXT DEFAULT '{}',
                version INTEGER DEFAULT 0,
                UNIQUE(run_id, event_id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_run_sequence ON events(run_id, sequence);

            CREATE TABLE IF NOT EXISTS manifests (
                run_id TEXT NOT NULL,
                manifest_kind TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                PRIMARY KEY (run_id, manifest_kind)
            );

            CREATE TABLE IF NOT EXISTS run_summaries (
                run_id TEXT PRIMARY KEY,
                first_sequence INTEGER,
                last_sequence INTEGER,
                event_count INTEGER DEFAULT 0,
                first_event_id TEXT,
                last_event_id TEXT,
                closed_at TEXT
            );
            """
        )
        self._conn.commit()

    def append(self, run_id: str, event: AuditEvent, expected_sequence: int | None = None) -> int:
        if event.run_id != run_id:
            raise ValueError(
                f"RUN_ID_MISMATCH arg={run_id} event.run_id={event.run_id}"
            )
        cursor = self._conn.execute(
            "SELECT COUNT(1) FROM events WHERE run_id = ? AND event_id = ?",
            (run_id, event.event_id),
        )
        if cursor.fetchone()[0] > 0:
            raise ValueError(
                f"DUPLICATE_EVENT run_id={run_id} event_id={event.event_id}"
            )

        cursor = self._conn.execute(
            "SELECT MAX(sequence) AS max_seq FROM events WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        next_seq = 1 if row["max_seq"] is None else row["max_seq"] + 1

        if expected_sequence is not None and expected_sequence != next_seq:
            raise ValueError(
                f"SEQUENCE_MISMATCH expected={expected_sequence} actual={next_seq}"
            )

        try:
            self._conn.execute(
                """
                INSERT INTO events (
                    run_id, sequence, event_id, timestamp, source, decision_kind,
                    node_id, actor, authority_ref, payload_summary, raw_payload_ref,
                    before, after, evidence_refs, annotations, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    next_seq,
                    event.event_id,
                    event.timestamp,
                    event.source,
                    event.decision_kind,
                    event.node_id,
                    event.actor,
                    event.authority_ref,
                    event.payload_summary,
                    event.raw_payload_ref,
                    json.dumps(event.before, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                    json.dumps(event.after, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                    json.dumps(list(event.evidence_refs), sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                    json.dumps(event.annotations, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                    event.version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"DUPLICATE_EVENT run_id={run_id} sequence={next_seq}") from exc

        self._conn.execute(
            """
            INSERT INTO runs (run_id, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (
                run_id,
                event.timestamp,
                event.timestamp,
                json.dumps({}, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            ),
        )

        self._conn.commit()
        return next_seq

    def events(self, run_id: str) -> list[AuditEvent]:
        cursor = self._conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        )
        events: list[AuditEvent] = []
        for row in cursor.fetchall():
            events.append(
                AuditEvent(
                    event_id=row["event_id"],
                    timestamp=row["timestamp"],
                    run_id=row["run_id"],
                    source=row["source"],
                    decision_kind=row["decision_kind"],
                    node_id=row["node_id"],
                    actor=row["actor"],
                    authority_ref=row["authority_ref"],
                    payload_summary=row["payload_summary"],
                    raw_payload_ref=row["raw_payload_ref"],
                    sequence=row["sequence"],
                    before=json.loads(row["before"]),
                    after=json.loads(row["after"]),
                    evidence_refs=tuple(json.loads(row["evidence_refs"])),
                    annotations=json.loads(row["annotations"]),
                    version=row["version"],
                )
            )
        return events

    def upsert_manifest(self, manifest: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO manifests (run_id, manifest_kind, schema_version, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, manifest_kind) DO UPDATE SET
                schema_version = excluded.schema_version,
                updated_at = excluded.updated_at,
                metadata = excluded.metadata
            """,
            (
                manifest.run_id,
                manifest.manifest_kind,
                manifest.schema_version,
                manifest.created_at,
                manifest.updated_at,
                json.dumps(manifest.metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def manifest(self, run_id: str, manifest_kind: str) -> Any | None:
        cursor = self._conn.execute(
            "SELECT * FROM manifests WHERE run_id = ? AND manifest_kind = ?",
            (run_id, manifest_kind),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return RunManifest(
            run_id=row["run_id"],
            manifest_kind=row["manifest_kind"],
            schema_version=row["schema_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"]),
        )

    def manifests(self, run_id: str) -> list[Any]:
        cursor = self._conn.execute(
            "SELECT * FROM manifests WHERE run_id = ? ORDER BY manifest_kind ASC",
            (run_id,),
        )
        return [
            RunManifest(
                run_id=row["run_id"],
                manifest_kind=row["manifest_kind"],
                schema_version=row["schema_version"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=json.loads(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    def upsert_summary(self, summary: Any) -> None:
        self._conn.execute(
            """
            INSERT INTO run_summaries (
                run_id, first_sequence, last_sequence, event_count,
                first_event_id, last_event_id, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                first_sequence = excluded.first_sequence,
                last_sequence = excluded.last_sequence,
                event_count = excluded.event_count,
                first_event_id = excluded.first_event_id,
                last_event_id = excluded.last_event_id,
                closed_at = excluded.closed_at
            """,
            (
                summary.run_id,
                summary.first_sequence,
                summary.last_sequence,
                summary.event_count,
                summary.first_event_id,
                summary.last_event_id,
                summary.closed_at,
            ),
        )
        self._conn.commit()

    def summary(self, run_id: str) -> Any | None:
        cursor = self._conn.execute(
            "SELECT * FROM run_summaries WHERE run_id = ?", (run_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return RunSummary(
            run_id=row["run_id"],
            first_sequence=row["first_sequence"],
            last_sequence=row["last_sequence"],
            event_count=row["event_count"],
            first_event_id=row["first_event_id"],
            last_event_id=row["last_event_id"],
            closed_at=row["closed_at"],
        )

    def query(self, run_id: str, decision_kind: str | None = None) -> list[AuditEvent]:
        if run_id == "*":
            sql = "SELECT * FROM events"
            params: list[Any] = []
        else:
            sql = "SELECT * FROM events WHERE run_id = ?"
            params = [run_id]
        if decision_kind is not None:
            if run_id != "*":
                sql += " AND decision_kind = ?"
            else:
                sql += " WHERE decision_kind = ?"
            params.append(decision_kind)
        sql += " ORDER BY sequence ASC"
        cursor = self._conn.execute(sql, params)
        events: list[AuditEvent] = []
        for row in cursor.fetchall():
            events.append(
                AuditEvent(
                    event_id=row["event_id"],
                    timestamp=row["timestamp"],
                    run_id=row["run_id"],
                    source=row["source"],
                    decision_kind=row["decision_kind"],
                    node_id=row["node_id"],
                    actor=row["actor"],
                    authority_ref=row["authority_ref"],
                    payload_summary=row["payload_summary"],
                    raw_payload_ref=row["raw_payload_ref"],
                    sequence=row["sequence"],
                    before=json.loads(row["before"]),
                    after=json.loads(row["after"]),
                    evidence_refs=tuple(json.loads(row["evidence_refs"])),
                    annotations=json.loads(row["annotations"]),
                    version=row["version"],
                )
            )
        return events

    def close(self) -> None:
        self._conn.close()
