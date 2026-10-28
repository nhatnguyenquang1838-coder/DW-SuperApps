"""LangGraph sidecar integration tests. The base package remains optional-import safe."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from importlib import import_module
from typing import Any

try:
    SqliteSaver: Any = import_module("langgraph.checkpoint.sqlite").SqliteSaver
    _LANGGRAPH_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    SqliteSaver = Any
    _LANGGRAPH_AVAILABLE = False

from dw_observation.events import RunProjectionEvent
from dw_observation.qualification_models import (
    CheckStatus,
    DwoRunId,
    ExecutionStatus,
    LangGraphThreadId,
    QualificationCheck,
    QualificationExecution,
    QualificationStatus,
    QualificationSubject,
    TaskRef,
    create_qualification_id,
    subject_digest,
)
from dw_observation.qualification_sources import ProjectionPrefix
from dw_observation.qualification_store import SQLiteQualificationReceiptStore, assert_storage_isolation
from dw_observation.qualification_graph import build_qualification_graph
from dw_observation.replay import ReplayTimeline


REQUIRED_SEMANTIC_CHECKS = (
    "hierarchy",
    "lifecycle",
    "dependency-blocking",
    "authority-orthogonality",
)


def make_subject(source_sha: str = "a" * 40, durable_position: str = "projection_ordinal=2") -> QualificationSubject:
    return QualificationSubject(
        dwo_run_id=DwoRunId("DWO-GRAPH-1"),
        task_ref=TaskRef("SCRUM-820"),
        source_repository="owner/gwc",
        source_sha=source_sha,
        lifecycle_profile="gwc.universal-run/1",
        projection_contract_version="dwo.projection-contract/2",
        reducer_version="dwo.reducer/1",
        durable_position=durable_position,
    )


def make_prefix(subject: QualificationSubject, *, checks=None, events=None, source_sha=None, durable_position=None) -> ProjectionPrefix:
    default_events = (
        RunProjectionEvent(
            occurred_at="2026-10-28T00:00:00Z",
            run_id=subject.dwo_run_id.value,
            source_event_id="evt-0",
            source_system="taskcontroller",
            source_digest="sha256:event-0",
            sequence=0,
            event_type="run_started",
        ),
        RunProjectionEvent(
            occurred_at="2026-10-28T00:00:01Z",
            run_id=subject.dwo_run_id.value,
            source_event_id="evt-1",
            source_system="taskcontroller",
            source_digest="sha256:event-1",
            sequence=1,
            event_type="node_completed",
            node_id="node-1",
            outcome="done",
        ),
    )
    semantic_checks = checks
    if semantic_checks is None:
        semantic_checks = tuple(
            QualificationCheck(name, CheckStatus.PASS, (f"evidence://{name}/1",))
            for name in REQUIRED_SEMANTIC_CHECKS
        )
    return ProjectionPrefix(
        dwo_run_id=subject.dwo_run_id,
        source_repository=subject.source_repository,
        source_sha=source_sha or subject.source_sha,
        lifecycle_profile=subject.lifecycle_profile,
        projection_contract_version=subject.projection_contract_version,
        reducer_version=subject.reducer_version,
        durable_position=durable_position or subject.durable_position,
        events=tuple(default_events if events is None else events),
        semantic_checks=tuple(semantic_checks),
    )


class MemoryProjectionSource:
    def __init__(self, prefix: ProjectionPrefix):
        self.prefix = prefix
        self.reads = 0

    def read_prefix(self, subject: QualificationSubject) -> ProjectionPrefix:
        self.reads += 1
        return self.prefix


class FailOnceReceiptStore:
    def __init__(self, delegate):
        self.delegate = delegate
        self.fail = True

    def put_idempotent(self, receipt):
        if self.fail:
            self.fail = False
            raise RuntimeError("simulated process interruption before receipt write")
        return self.delegate.put_idempotent(receipt)

    def count(self):
        return self.delegate.count()

    def get_for_run(self, *args, **kwargs):
        return self.delegate.get_for_run(*args, **kwargs)


@unittest.skipUnless(_LANGGRAPH_AVAILABLE, "install the optional qualification extra")
class QualificationGraphTests(unittest.TestCase):
    def _invoke(self, graph, subject, thread_value: str):
        execution = QualificationExecution(
            qualification_id=create_qualification_id(subject, "graph/1"),
            subject_digest=subject_digest(subject),
            langgraph_thread_id=LangGraphThreadId(thread_value),
            graph_version="graph/1",
            status=ExecutionStatus.PENDING,
        )
        return graph.invoke(
            {"subject": subject.to_dict(), "execution": execution.to_dict()},
            config={"configurable": {"thread_id": execution.langgraph_thread_id.value}},
        )

    def test_graph_uses_pure_python_reducer_replay_and_emits_deterministic_receipt(self):
        subject = make_subject()
        prefix = make_prefix(subject)
        source = MemoryProjectionSource(prefix)
        before = tuple(event.to_dict() for event in prefix.events)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint_path = root / "langgraph-checkpoints.sqlite"
            receipt_path = root / "qualification-receipts.sqlite"
            projection_path = root / "projection-events.sqlite"
            with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpoint:
                checkpoint.setup()
                with SQLiteQualificationReceiptStore(receipt_path) as store:
                    assert_storage_isolation(checkpoint_path, receipt_path, projection_path)
                    graph = build_qualification_graph(source, store, "graph/1", checkpointer=checkpoint)
                    result = self._invoke(graph, subject, "langgraph:thread-1")
                    receipt = result["receipt"]
                    self.assertEqual(receipt["status"], QualificationStatus.QUALIFIED.value)
                    self.assertEqual(receipt["subject_digest"], subject_digest(subject))
                    self.assertFalse(receipt["authority_granted"])
                    self.assertFalse(receipt["projection_events_mutated"])
                    self.assertEqual(store.count(), 1)
                    self.assertGreater(source.reads, 0)
                    self.assertEqual(tuple(event.to_dict() for event in prefix.events), before)
                    replay = ReplayTimeline(prefix.events)
                    self.assertTrue(replay.verify_determinism())
                    self.assertEqual(replay.tip().projection.run_id, subject.dwo_run_id.value)

                    # Same subject on a distinct operational thread reuses the
                    # deterministic receipt without duplicating durable rows.
                    repeated = self._invoke(graph, subject, "langgraph:thread-2")
                    self.assertEqual(repeated["receipt"]["receipt_digest"], receipt["receipt_digest"])
                    self.assertEqual(store.count(), 1)

    def test_missing_v2_semantic_evidence_never_becomes_qualified(self):
        subject = make_subject()
        unknown_checks = tuple(
            QualificationCheck(name, CheckStatus.UNKNOWN, (f"evidence://missing/{name}",))
            for name in REQUIRED_SEMANTIC_CHECKS
        )
        source = MemoryProjectionSource(make_prefix(subject, checks=unknown_checks))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with SqliteSaver.from_conn_string(str(root / "checkpoints.sqlite")) as checkpoint:
                checkpoint.setup()
                with SQLiteQualificationReceiptStore(root / "receipts.sqlite") as store:
                    graph = build_qualification_graph(source, store, "graph/1", checkpointer=checkpoint)
                    result = self._invoke(graph, subject, "langgraph:unknown-1")
                    self.assertEqual(result["receipt"]["status"], QualificationStatus.UNKNOWN.value)
                    self.assertEqual(store.count(), 1)

    def test_source_drift_emits_drifted_receipt_without_reusing_old_subject(self):
        subject = make_subject()
        drifted = MemoryProjectionSource(make_prefix(subject, source_sha="b" * 40))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with SqliteSaver.from_conn_string(str(root / "checkpoints.sqlite")) as checkpoint:
                checkpoint.setup()
                with SQLiteQualificationReceiptStore(root / "receipts.sqlite") as store:
                    graph = build_qualification_graph(drifted, store, "graph/1", checkpointer=checkpoint)
                    result = self._invoke(graph, subject, "langgraph:drift-1")
                    self.assertEqual(result["receipt"]["status"], QualificationStatus.DRIFTED.value)
                    self.assertNotEqual(result["receipt"]["subject_digest"], "")
                    self.assertEqual(store.count(), 1)

    def test_interruption_resume_persists_receipt_once(self):
        subject = make_subject()
        source = MemoryProjectionSource(make_prefix(subject))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with SqliteSaver.from_conn_string(str(root / "checkpoints.sqlite")) as checkpoint:
                checkpoint.setup()
                with SQLiteQualificationReceiptStore(root / "receipts.sqlite") as store:
                    flaky_store = FailOnceReceiptStore(store)
                    graph = build_qualification_graph(source, flaky_store, "graph/1", checkpointer=checkpoint)
                    execution = QualificationExecution(
                        qualification_id=create_qualification_id(subject, "graph/1"),
                        subject_digest=subject_digest(subject),
                        langgraph_thread_id=LangGraphThreadId("langgraph:resume-1"),
                        graph_version="graph/1",
                        status=ExecutionStatus.PENDING,
                    )
                    config = {"configurable": {"thread_id": execution.langgraph_thread_id.value}}
                    inputs = {"subject": subject.to_dict(), "execution": execution.to_dict()}
                    with self.assertRaises(RuntimeError):
                        graph.invoke(inputs, config=config)
                    self.assertEqual(store.count(), 0)
                    resumed = graph.invoke(inputs, config=config)
                    self.assertEqual(resumed["receipt"]["status"], QualificationStatus.QUALIFIED.value)
                    self.assertEqual(store.count(), 1)

    def test_checkpoint_state_contains_digests_not_projection_event_history(self):
        subject = make_subject()
        prefix = make_prefix(subject)
        source = MemoryProjectionSource(prefix)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with SqliteSaver.from_conn_string(str(root / "checkpoints.sqlite")) as checkpoint:
                checkpoint.setup()
                with SQLiteQualificationReceiptStore(root / "receipts.sqlite") as store:
                    graph = build_qualification_graph(source, store, "graph/1", checkpointer=checkpoint)
                    execution = QualificationExecution(
                        qualification_id=create_qualification_id(subject, "graph/1"),
                        subject_digest=subject_digest(subject),
                        langgraph_thread_id=LangGraphThreadId("langgraph:checkpoint-1"),
                        graph_version="graph/1",
                        status=ExecutionStatus.PENDING,
                    )
                    config = {"configurable": {"thread_id": execution.langgraph_thread_id.value}}
                    graph.invoke({"subject": subject.to_dict(), "execution": execution.to_dict()}, config=config)
                    snapshots = list(graph.get_state_history(config))
                    serialized = repr([snapshot.values for snapshot in snapshots])
                    self.assertIn(prefix.history_digest, serialized)
                    self.assertNotIn("evt-0", serialized)
                    self.assertNotIn("evt-1", serialized)


if __name__ == "__main__":
    unittest.main()
