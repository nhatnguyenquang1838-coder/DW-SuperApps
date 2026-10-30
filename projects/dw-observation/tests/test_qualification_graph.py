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


class SemanticVerifierContractTests(unittest.TestCase):
    def _evidence(self, subject=None, *, facts=None, **overrides):
        from dw_observation.qualification_semantics import SemanticEvidence

        subject = subject or make_subject()
        prefix = make_prefix(subject, checks=())
        values = {
            "source_repository": subject.source_repository,
            "source_sha": subject.source_sha,
            "projection_contract_version": subject.projection_contract_version,
            "reducer_version": subject.reducer_version,
            "subject_digest": subject_digest(subject),
            "history_digest": prefix.history_digest,
            "facts": facts or {
                "hierarchy": {"nodes": [{"id": "root", "parent_id": None}, {"id": "child", "parent_id": "root"}]},
                "lifecycle": {"transitions": [{"sequence": 1, "from": "PENDING", "to": "RUNNING"}, {"sequence": 2, "from": "RUNNING", "to": "COMPLETED"}]},
                "dependencies": {"nodes": [{"id": "build", "status": "COMPLETED"}, {"id": "deploy", "status": "COMPLETED"}], "edges": [{"predecessor": "build", "successor": "deploy"}]},
                "authority": {"lifecycle_terminal": "COMPLETED", "authority_decision": "NOT_GRANTED", "protected_effect_observed": False},
            },
        }
        values.update(overrides)
        return SemanticEvidence.create(**values), prefix

    def test_self_attested_source_bound_facts_cannot_qualify_semantics(self):
        from dw_observation.qualification_semantics import verify_semantic_evidence

        subject = make_subject()
        evidence, prefix = self._evidence(subject)
        result = verify_semantic_evidence(evidence, subject, prefix)
        self.assertEqual([check.status for check in result], [CheckStatus.UNKNOWN] * 4)
        self.assertEqual(tuple(check.check_id for check in result), REQUIRED_SEMANTIC_CHECKS)

    def test_missing_evidence_and_unchecked_pass_claims_are_unknown(self):
        from dw_observation.qualification_semantics import verify_semantic_evidence

        subject = make_subject()
        prefix = make_prefix(subject)
        self.assertTrue(all(check.status is CheckStatus.PASS for check in prefix.semantic_checks))
        result = verify_semantic_evidence(prefix.semantic_evidence, subject, prefix)
        self.assertEqual([check.status for check in result], [CheckStatus.UNKNOWN] * 4)

    def test_mismatched_source_binding_is_drifted(self):
        from dw_observation.qualification_semantics import verify_semantic_evidence

        subject = make_subject()
        evidence, prefix = self._evidence(subject, source_sha="b" * 40)
        result = verify_semantic_evidence(evidence, subject, prefix)
        self.assertEqual([check.status for check in result], [CheckStatus.DRIFTED] * 4)

    def test_changed_event_history_boundary_is_drifted(self):
        from dw_observation.qualification_semantics import verify_semantic_evidence

        subject = make_subject()
        evidence, prefix = self._evidence(subject, history_digest="sha256:" + "0" * 64)
        result = verify_semantic_evidence(evidence, subject, prefix)
        self.assertEqual([check.status for check in result], [CheckStatus.DRIFTED] * 4)

    def test_tampered_facts_digest_is_unknown(self):
        from dataclasses import replace
        from dw_observation.qualification_semantics import verify_semantic_evidence

        subject = make_subject()
        evidence, prefix = self._evidence(subject)
        tampered = replace(evidence, facts={**evidence.facts, "authority": {"lifecycle_terminal": "COMPLETED", "authority_decision": "GRANTED", "protected_effect_observed": True}})
        result = verify_semantic_evidence(tampered, subject, prefix)
        self.assertEqual([check.status for check in result], [CheckStatus.UNKNOWN] * 4)

    def test_contradictory_dependency_facts_fail_independently(self):
        from dw_observation.qualification_semantics import verify_semantic_evidence

        facts = {
            "hierarchy": {"nodes": [{"id": "root", "parent_id": None}]},
            "lifecycle": {"transitions": [{"sequence": 1, "from": "PENDING", "to": "COMPLETED"}]},
            "dependencies": {"nodes": [{"id": "build", "status": "FAILED"}, {"id": "deploy", "status": "COMPLETED"}], "edges": [{"predecessor": "build", "successor": "deploy"}]},
            "authority": {"lifecycle_terminal": "COMPLETED", "authority_decision": "NOT_GRANTED", "protected_effect_observed": False},
        }
        evidence, prefix = self._evidence(facts=facts)
        result = verify_semantic_evidence(evidence, make_subject(), prefix)
        by_id = {check.check_id: check.status for check in result}
        self.assertEqual([check.status for check in result], [CheckStatus.UNKNOWN] * 4)

    def test_hierarchy_cycle_and_lifecycle_jump_fail_their_checks(self):
        from dw_observation.qualification_semantics import verify_semantic_evidence

        facts = {
            "hierarchy": {"nodes": [{"id": "a", "parent_id": "b"}, {"id": "b", "parent_id": "a"}]},
            "lifecycle": {"transitions": [{"sequence": 1, "from": "PENDING", "to": "COMPLETED"}]},
            "dependencies": {"nodes": [{"id": "one", "status": "COMPLETED"}], "edges": []},
            "authority": {"lifecycle_terminal": "COMPLETED", "authority_decision": "GRANTED", "protected_effect_observed": False},
        }
        evidence, prefix = self._evidence(facts=facts)
        result = verify_semantic_evidence(evidence, make_subject(), prefix)
        by_id = {check.check_id: check.status for check in result}
        self.assertEqual([check.status for check in result], [CheckStatus.UNKNOWN] * 4)

    def test_unknown_schema_is_unknown(self):
        from dataclasses import replace
        from dw_observation.qualification_semantics import verify_semantic_evidence

        subject = make_subject()
        evidence, prefix = self._evidence(subject)
        result = verify_semantic_evidence(replace(evidence, schema_version="dwo.semantic-evidence/999"), subject, prefix)
        self.assertEqual([check.status for check in result], [CheckStatus.UNKNOWN] * 4)


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


def make_verified_prefix(subject: QualificationSubject) -> ProjectionPrefix:
    from dataclasses import replace
    from dw_observation.qualification_semantics import SemanticEvidence

    prefix = make_prefix(subject, checks=())
    facts = {
        "hierarchy": {"nodes": [{"id": "root", "parent_id": None}, {"id": "child", "parent_id": "root"}]},
        "lifecycle": {"transitions": [{"sequence": 1, "from": "PENDING", "to": "RUNNING"}, {"sequence": 2, "from": "RUNNING", "to": "COMPLETED"}]},
        "dependencies": {"nodes": [{"id": "build", "status": "COMPLETED"}, {"id": "deploy", "status": "COMPLETED"}], "edges": [{"predecessor": "build", "successor": "deploy"}]},
        "authority": {"lifecycle_terminal": "COMPLETED", "authority_decision": "NOT_GRANTED", "protected_effect_observed": False},
    }
    evidence = SemanticEvidence.create(
        source_repository=subject.source_repository, source_sha=subject.source_sha,
        projection_contract_version=subject.projection_contract_version,
        reducer_version=subject.reducer_version, subject_digest=subject_digest(subject),
        history_digest=prefix.history_digest, facts=facts,
    )
    return replace(prefix, semantic_evidence=evidence)


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
        prefix = make_verified_prefix(subject)
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
                    self.assertEqual(receipt["status"], QualificationStatus.UNKNOWN.value)
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
        source = MemoryProjectionSource(make_verified_prefix(subject))
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
                    self.assertEqual(resumed["receipt"]["status"], QualificationStatus.UNKNOWN.value)
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
