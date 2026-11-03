"""Contract tests for the DWO LangGraph qualification identity models."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from dw_observation.qualification_models import (
    DwoRunId,
    ExecutionStatus,
    LangGraphThreadId,
    QualificationCheck,
    QualificationExecution,
    QualificationId,
    QualificationReceipt,
    QualificationStatus,
    QualificationSubject,
    TaskRef,
    create_qualification_id,
    create_qualification_receipt,
    subject_digest,
)


def subject(**overrides) -> QualificationSubject:
    values = {
        "dwo_run_id": DwoRunId("DWO-RUN-001"),
        "task_ref": TaskRef("SCRUM-820"),
        "source_repository": "nhatnguyenquang1838-coder/gwc",
        "source_sha": "a" * 40,
        "lifecycle_profile": "gwc.universal-run/1",
        "projection_contract_version": "dwo.projection-contract/2",
        "reducer_version": "dwo.reducer/1",
        "durable_position": "projection_ordinal=7",
    }
    values.update(overrides)
    return QualificationSubject(**values)


class QualificationSubjectTests(unittest.TestCase):
    def test_serialization_keeps_run_task_qualification_and_thread_namespaces_separate(self):
        value = subject()
        execution = QualificationExecution(
            qualification_id=create_qualification_id(value, "graph/1"),
            subject_digest=subject_digest(value),
            langgraph_thread_id=LangGraphThreadId("langgraph:thread-001"),
            graph_version="graph/1",
            status=ExecutionStatus.PENDING,
        )
        payload = {"subject": value.to_dict(), "execution": execution.to_dict()}
        self.assertEqual(payload["subject"]["dwo_run_id"], "DWO-RUN-001")
        self.assertEqual(payload["subject"]["task_ref"], "SCRUM-820")
        self.assertEqual(payload["execution"]["qualification_id"], execution.qualification_id.value)
        self.assertEqual(payload["execution"]["langgraph_thread_id"], "langgraph:thread-001")
        self.assertNotIn("run_id", payload["execution"])

    def test_identical_subjects_have_identical_digests_and_material_drift_changes_digest(self):
        original = subject()
        self.assertEqual(subject_digest(original), subject_digest(subject()))
        self.assertNotEqual(subject_digest(original), subject_digest(subject(source_sha="b" * 40)))
        self.assertNotEqual(subject_digest(original), subject_digest(subject(durable_position="projection_ordinal=8")))

    def test_source_sha_must_be_exact_lowercase_sha256(self):
        for invalid in ("a" * 39, "A" * 40, "z" * 40, ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    subject(source_sha=invalid)

    def test_task_ref_may_be_null_but_never_an_empty_string(self):
        self.assertIsNone(subject(task_ref=None).task_ref)
        with self.assertRaises(ValueError):
            subject(task_ref=TaskRef(""))

    def test_models_round_trip_without_collapsing_identity_fields(self):
        value = subject()
        decoded = QualificationSubject.from_dict(value.to_dict())
        self.assertEqual(decoded, value)
        self.assertEqual(decoded.to_dict(), value.to_dict())


class QualificationExecutionAndReceiptTests(unittest.TestCase):
    def test_execution_round_trip_preserves_status_and_thread_namespace(self):
        value = subject()
        qualification_id = create_qualification_id(value, "graph/1")
        execution = QualificationExecution(
            qualification_id=qualification_id,
            subject_digest=subject_digest(value),
            langgraph_thread_id=LangGraphThreadId("langgraph:run-001"),
            graph_version="graph/1",
            status=ExecutionStatus.INTERRUPTED,
            evidence_refs=("evidence://projection/7",),
        )
        decoded = QualificationExecution.from_dict(execution.to_dict())
        self.assertEqual(decoded, execution)
        self.assertEqual(decoded.status, ExecutionStatus.INTERRUPTED)

    def test_receipt_is_immutable_deterministic_and_never_grants_authority(self):
        value = subject()
        checks = (
            QualificationCheck("reducer-parity", "PASS", ("evidence://replay/7",)),
            QualificationCheck("subject-current", "PASS", ("evidence://source/sha",)),
        )
        first = create_qualification_receipt(value, "graph/1", QualificationStatus.QUALIFIED, checks)
        second = create_qualification_receipt(value, "graph/1", QualificationStatus.QUALIFIED, checks)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertFalse(first.authority_granted)
        self.assertFalse(first.projection_events_mutated)
        with self.assertRaises(FrozenInstanceError):
            first.status = QualificationStatus.FAILED

    def test_same_qualification_id_binds_exact_subject_and_graph_version(self):
        original = subject()
        self.assertEqual(create_qualification_id(original, "graph/1"), create_qualification_id(subject(), "graph/1"))
        self.assertNotEqual(create_qualification_id(original, "graph/1"), create_qualification_id(subject(source_sha="b" * 40), "graph/1"))
        self.assertNotEqual(create_qualification_id(original, "graph/1"), create_qualification_id(original, "graph/2"))

    def test_execution_rejects_qualification_id_bound_to_a_different_subject(self):
        value = subject()
        other = subject(source_sha="b" * 40)
        with self.assertRaises(ValueError):
            QualificationExecution(
                qualification_id=create_qualification_id(other, "graph/1"),
                subject_digest=subject_digest(value),
                langgraph_thread_id=LangGraphThreadId("langgraph:thread-001"),
                graph_version="graph/1",
                status=ExecutionStatus.PENDING,
            )

    def test_receipt_round_trip_verifies_canonical_digest(self):
        receipt = create_qualification_receipt(
            subject(),
            "graph/1",
            QualificationStatus.UNKNOWN,
            (QualificationCheck("hierarchy-evidence", "UNKNOWN", ("evidence://missing/hierarchy",)),),
        )
        self.assertEqual(QualificationReceipt.from_dict(receipt.to_dict()), receipt)
        corrupted = receipt.to_dict()
        corrupted["subject"]["source_sha"] = "b" * 40
        with self.assertRaises(ValueError):
            QualificationReceipt.from_dict(corrupted)

    def test_receipt_rejects_authority_or_projection_history_mutation(self):
        value = subject()
        with self.assertRaises(ValueError):
            QualificationReceipt(
                receipt_id="receipt:bad",
                qualification_id=create_qualification_id(value, "graph/1"),
                subject=value,
                subject_digest=subject_digest(value),
                graph_version="graph/1",
                status=QualificationStatus.QUALIFIED,
                checks=(),
                evidence_refs=(),
                authority_granted=True,
            )
        with self.assertRaises(ValueError):
            QualificationReceipt(
                receipt_id="receipt:bad",
                qualification_id=create_qualification_id(value, "graph/1"),
                subject=value,
                subject_digest=subject_digest(value),
                graph_version="graph/1",
                status=QualificationStatus.QUALIFIED,
                checks=(),
                evidence_refs=(),
                projection_events_mutated=True,
            )


if __name__ == "__main__":
    unittest.main()
