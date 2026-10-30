"""Persistence contract tests for isolated, idempotent qualification receipts."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from dw_observation.qualification_models import (
    CheckStatus,
    DwoRunId,
    QualificationCheck,
    QualificationStatus,
    QualificationSubject,
    TaskRef,
    create_qualification_receipt,
)
from dw_observation.qualification_store import (
    QualificationReceiptConflict,
    SQLiteQualificationReceiptStore,
    assert_storage_isolation,
)


def sample_subject() -> QualificationSubject:
    return QualificationSubject(
        dwo_run_id=DwoRunId("DWO-RUN-STORE-1"),
        task_ref=TaskRef("SCRUM-820"),
        source_repository="owner/gwc",
        source_sha="a" * 40,
        lifecycle_profile="gwc.universal-run/1",
        projection_contract_version="dwo.projection-contract/2",
        reducer_version="dwo.reducer/1",
        durable_position="projection_ordinal=11",
    )


def sample_receipt(status: QualificationStatus = QualificationStatus.QUALIFIED):
    checks = (
        QualificationCheck("history-parity", CheckStatus.PASS, ("evidence://history/11",)),
    ) if status is QualificationStatus.QUALIFIED else (
        QualificationCheck("history-parity", CheckStatus.UNKNOWN, ("evidence://history/unavailable",)),
    )
    return create_qualification_receipt(sample_subject(), "graph/1", status, checks)


class QualificationReceiptStoreTests(unittest.TestCase):
    def test_receipt_write_is_idempotent_and_readback_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qualification-receipts.sqlite"
            receipt = sample_receipt()
            with SQLiteQualificationReceiptStore(path) as store:
                first = store.put_idempotent(receipt)
                second = store.put_idempotent(receipt)
                self.assertEqual(first, receipt)
                self.assertEqual(second, receipt)
                self.assertEqual(store.count(), 1)
                self.assertEqual(store.get(receipt.qualification_id), receipt)
                self.assertEqual(store.get_for_run(receipt.subject.dwo_run_id), (receipt,))

    def test_conflicting_duplicate_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qualification-receipts.sqlite"
            qualified = sample_receipt(QualificationStatus.QUALIFIED)
            unknown = sample_receipt(QualificationStatus.UNKNOWN)
            self.assertEqual(qualified.qualification_id, unknown.qualification_id)
            with SQLiteQualificationReceiptStore(path) as store:
                store.put_idempotent(qualified)
                with self.assertRaises(QualificationReceiptConflict):
                    store.put_idempotent(unknown)
                self.assertEqual(store.count(), 1)

    def test_receipt_store_is_separate_from_checkpoint_and_canonical_history_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "langgraph-checkpoints.sqlite"
            receipts = root / "qualification-receipts.sqlite"
            projection_events = root / "projection-events.sqlite"
            assert_storage_isolation(checkpoint, receipts, projection_events)
            with self.assertRaises(ValueError):
                assert_storage_isolation(checkpoint, checkpoint, projection_events)
            with self.assertRaises(ValueError):
                assert_storage_isolation(checkpoint, projection_events, projection_events)

    def test_read_only_store_does_not_create_missing_database_and_cannot_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.sqlite"
            with self.assertRaises(FileNotFoundError):
                SQLiteQualificationReceiptStore(path, read_only=True)
            self.assertFalse(path.exists())

    def test_receipt_write_does_not_touch_projection_events_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projection = root / "projection-events.sqlite"
            connection = sqlite3.connect(projection)
            try:
                connection.execute("CREATE TABLE projection_events (run_id TEXT NOT NULL)")
                connection.execute("INSERT INTO projection_events VALUES ('R-1')")
                connection.commit()
            finally:
                connection.close()
            with SQLiteQualificationReceiptStore(root / "qualification-receipts.sqlite") as store:
                store.put_idempotent(sample_receipt())
            connection = sqlite3.connect(projection)
            try:
                rows = connection.execute("SELECT run_id FROM projection_events").fetchall()
            finally:
                connection.close()
            self.assertEqual(rows, [("R-1",)])


if __name__ == "__main__":
    unittest.main()
