"""Read-only semantic-qualification projection tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dw_observation.qualification_models import (
    CheckStatus,
    DwoRunId,
    ExecutionStatus,
    QualificationCheck,
    QualificationReceipt,
    QualificationStatus,
    QualificationSubject,
    TaskRef,
    create_qualification_receipt,
)
from dw_observation.qualification_store import SQLiteQualificationReceiptStore
from dw_observation.qualification_projection import QualificationProjectionService


GRAPH_VERSION = "graph/1"


def make_subject(source_sha: str = "a" * 40) -> QualificationSubject:
    return QualificationSubject(
        dwo_run_id=DwoRunId("DWO-PROJECTION-1"),
        task_ref=TaskRef("SCRUM-820"),
        source_repository="owner/gwc",
        source_sha=source_sha,
        lifecycle_profile="gwc.universal-run/1",
        projection_contract_version="dwo.projection-contract/2",
        reducer_version="dwo.reducer/1",
        durable_position="projection_ordinal=8",
    )


def qualified_receipt(subject: QualificationSubject, graph_version: str = GRAPH_VERSION) -> QualificationReceipt:
    checks = (
        QualificationCheck("reducer-replay-parity", CheckStatus.PASS, ("evidence://replay/1",)),
        QualificationCheck("hierarchy", CheckStatus.PASS, ("evidence://hierarchy/1",)),
    )
    return create_qualification_receipt(subject, graph_version, QualificationStatus.QUALIFIED, checks)


class CurrentSubjectReader:
    def __init__(self, subject: QualificationSubject | None):
        self.subject = subject
        self.calls = []

    def read_current_subject(self, run_id: DwoRunId) -> QualificationSubject | None:
        self.calls.append(run_id.value)
        return self.subject


class ProgressReader:
    def __init__(self, status: ExecutionStatus | None):
        self.status = status
        self.calls = []

    def read_status(self, run_id: DwoRunId, current_subject_digest: str) -> ExecutionStatus | None:
        self.calls.append((run_id.value, current_subject_digest))
        return self.status


class QualificationProjectionServiceTests(unittest.TestCase):
    def test_absent_receipt_is_unknown_even_for_current_subject(self):
        subject = make_subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path):
                pass
            with SQLiteQualificationReceiptStore(path, read_only=True) as store:
                reader = CurrentSubjectReader(subject)
                result = QualificationProjectionService(store, reader, graph_version=GRAPH_VERSION).read(subject.dwo_run_id)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["current_subject_digest"], result["subject_digest"])
                self.assertIsNone(result["receipt_id"])
                self.assertFalse(result["authority_granted"])
                self.assertFalse(result["projection_events_mutated"])

    def test_exact_subject_receipt_is_qualified_and_read_only(self):
        subject = make_subject()
        receipt = qualified_receipt(subject)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path) as writer:
                writer.put_idempotent(receipt)
            with SQLiteQualificationReceiptStore(path, read_only=True) as reader:
                result = QualificationProjectionService(reader, CurrentSubjectReader(subject), graph_version=GRAPH_VERSION).read(subject.dwo_run_id)
                self.assertEqual(result["status"], "QUALIFIED")
                self.assertEqual(result["receipt_id"], receipt.receipt_id)
                self.assertEqual(result["receipt_subject_digest"], result["current_subject_digest"])
                self.assertEqual(result["source_sha"], subject.source_sha)
                self.assertEqual(result["durable_position"], subject.durable_position)
                self.assertEqual(result["evidence_refs"], list(receipt.evidence_refs))
                self.assertFalse(result["authority_granted"])
                self.assertFalse(result["projection_events_mutated"])
                with self.assertRaises(PermissionError):
                    reader.put_idempotent(receipt)

    def test_changed_subject_without_a_current_receipt_is_drifted(self):
        old_subject = make_subject("a" * 40)
        current_subject = make_subject("b" * 40)
        old_receipt = qualified_receipt(old_subject)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path) as writer:
                writer.put_idempotent(old_receipt)
            with SQLiteQualificationReceiptStore(path, read_only=True) as reader:
                result = QualificationProjectionService(reader, CurrentSubjectReader(current_subject), graph_version=GRAPH_VERSION).read(current_subject.dwo_run_id)
                self.assertEqual(result["status"], "DRIFTED")
                self.assertIsNone(result["receipt_id"])
                self.assertNotEqual(result["current_subject_digest"], old_receipt.subject_digest)

    def test_running_execution_projects_qualifying_without_reading_checkpointer(self):
        subject = make_subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path):
                pass
            with SQLiteQualificationReceiptStore(path, read_only=True) as reader:
                progress = ProgressReader(ExecutionStatus.RUNNING)
                result = QualificationProjectionService(
                    reader,
                    CurrentSubjectReader(subject),
                    graph_version=GRAPH_VERSION,
                    progress_reader=progress,
                ).read(subject.dwo_run_id)
                self.assertEqual(result["status"], "QUALIFYING")
                self.assertEqual(progress.calls[0][0], subject.dwo_run_id.value)
                self.assertEqual(len(progress.calls[0][1]), 71)

    def test_failed_progress_is_not_qualified_and_source_absence_is_unknown(self):
        subject = make_subject()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path):
                pass
            with SQLiteQualificationReceiptStore(path, read_only=True) as reader:
                failed = QualificationProjectionService(
                    reader,
                    CurrentSubjectReader(subject),
                    graph_version=GRAPH_VERSION,
                    progress_reader=ProgressReader(ExecutionStatus.FAILED),
                ).read(subject.dwo_run_id)
                self.assertEqual(failed["status"], "FAILED")
                missing = QualificationProjectionService(reader, CurrentSubjectReader(None), graph_version=GRAPH_VERSION).read(subject.dwo_run_id)
                self.assertEqual(missing["status"], "UNKNOWN")
                self.assertIsNone(missing["current_subject_digest"])

    def test_graph_version_drift_does_not_reuse_old_receipt(self):
        subject = make_subject()
        old_receipt = qualified_receipt(subject, "graph/old")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path) as writer:
                writer.put_idempotent(old_receipt)
            with SQLiteQualificationReceiptStore(path, read_only=True) as reader:
                result = QualificationProjectionService(
                    reader,
                    CurrentSubjectReader(subject),
                    graph_version=GRAPH_VERSION,
                ).read(subject.dwo_run_id)
                self.assertEqual(result["status"], "DRIFTED")
                self.assertIsNone(result["receipt_id"])

    def test_service_requires_a_read_only_receipt_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path) as writer:
                with self.assertRaises(ValueError):
                    QualificationProjectionService(writer, CurrentSubjectReader(make_subject()), graph_version=GRAPH_VERSION)


if __name__ == "__main__":
    unittest.main()
