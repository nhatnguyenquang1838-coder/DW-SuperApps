"""Deterministic LangGraph qualification sidecar for DWO projection prefixes.

The graph persists operational progress only in a LangGraph checkpointer. It
re-reads the exact canonical prefix by immutable boundary, calls the existing
pure reducer/replay functions, and writes only an immutable qualification
receipt to a separate store. No node has a projection-event writer or runtime
mutation capability.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
import json
from pathlib import Path
from typing import Any, Iterator, Protocol, TypedDict

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    class RunnableConfig(TypedDict, total=False):
        configurable: dict[str, Any]

from .qualification_models import (
    CheckStatus,
    ExecutionStatus,
    QualificationCheck,
    QualificationExecution,
    QualificationReceipt,
    QualificationStatus,
    QualificationSubject,
    create_qualification_id,
    create_qualification_receipt,
    subject_digest,
)
from .qualification_sources import (
    ProjectionPrefix,
    ProjectionSourceUnavailable,
    ReadOnlyProjectionSource,
    validate_prefix_binding,
)
from .qualification_semantics import REQUIRED_SEMANTIC_CHECKS, verify_semantic_evidence
from .qualification_store import SQLiteQualificationReceiptStore, assert_storage_isolation
from .reducer import reduce as reduce_events
from .replay import ReplayTimeline


GRAPH_VERSION = "dwo.langgraph-qualification/1"

try:
    _langgraph_graph = import_module("langgraph.graph")
    _langgraph_checkpoint_sqlite = import_module("langgraph.checkpoint.sqlite")
    _START = _langgraph_graph.START
    _END = _langgraph_graph.END
    _StateGraph = _langgraph_graph.StateGraph
    _SqliteSaver = _langgraph_checkpoint_sqlite.SqliteSaver
    LANGGRAPH_AVAILABLE = True
except (ImportError, AttributeError):
    _START = _END = _StateGraph = _SqliteSaver = None
    LANGGRAPH_AVAILABLE = False


class QualificationGraphState(TypedDict, total=False):
    subject: dict[str, Any]
    execution: dict[str, Any]
    graph_version: str
    terminal_status: str
    checks: list[dict[str, Any]]
    evidence_refs: list[str]
    history_digest: str
    semantic_facts_digest: str
    event_count: int
    projection_digest: str
    replay_digest: str
    receipt: dict[str, Any]
    receipt_ref: str
    error_code: str


class QualificationReceiptWriter(Protocol):
    def put_idempotent(self, receipt: QualificationReceipt) -> QualificationReceipt: ...


class LangGraphUnavailable(RuntimeError):
    """The optional LangGraph qualification dependencies are not installed."""


class QualificationInputError(ValueError):
    """The supplied subject/execution binding is internally inconsistent."""


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    import hashlib

    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _check_from_dict(value: dict[str, Any]) -> QualificationCheck:
    return QualificationCheck.from_dict(value)


def _append_check(state: QualificationGraphState, check: QualificationCheck) -> dict[str, Any]:
    checks = list(state.get("checks", []))
    existing = next((index for index, row in enumerate(checks) if row.get("check_id") == check.check_id), None)
    if existing is None:
        checks.append(check.to_dict())
    else:
        checks[existing] = check.to_dict()
    refs = set(state.get("evidence_refs", []))
    refs.update(check.evidence_refs)
    return {"checks": checks, "evidence_refs": sorted(refs)}


def _evidence_ref(kind: str, digest: str) -> str:
    return f"evidence://dwo-qualification/{kind}/{digest.removeprefix('sha256:')}"


def _prefix_or_drift(
    source: ReadOnlyProjectionSource,
    subject: QualificationSubject,
    expected_history_digest: str | None = None,
    expected_facts_digest: str | None = None,
) -> tuple[ProjectionPrefix | None, str | None]:
    prefix = source.read_prefix(subject)
    binding = validate_prefix_binding(prefix, subject)
    if binding.status is CheckStatus.DRIFTED:
        return prefix, "SUBJECT_DRIFT"
    if binding.status is CheckStatus.UNKNOWN:
        return prefix, "PREFIX_UNKNOWN"
    if expected_history_digest is not None and prefix.history_digest != expected_history_digest:
        return prefix, "HISTORY_BOUNDARY_DRIFT"
    facts_digest = prefix.semantic_facts_digest
    if expected_facts_digest is not None and facts_digest != expected_facts_digest:
        return prefix, "SEMANTIC_EVIDENCE_DRIFT"
    return prefix, None


def _terminal(state: QualificationGraphState) -> bool:
    return bool(state.get("terminal_status"))


def _make_graph_receipt(state: QualificationGraphState, graph_version: str) -> QualificationGraphState:
    subject = QualificationSubject.from_dict(state["subject"])
    status_value = state.get("terminal_status")
    if status_value is None:
        checks = [_check_from_dict(row) for row in state.get("checks", [])]
        if any(check.status is CheckStatus.DRIFTED for check in checks):
            status = QualificationStatus.DRIFTED
        elif any(check.status is CheckStatus.FAIL for check in checks):
            status = QualificationStatus.FAILED
        elif any(check.status is CheckStatus.UNKNOWN for check in checks):
            status = QualificationStatus.UNKNOWN
        elif checks and all(check.status is CheckStatus.PASS for check in checks):
            status = QualificationStatus.QUALIFIED
        else:
            status = QualificationStatus.UNKNOWN
    else:
        status = QualificationStatus(status_value)
        checks = [_check_from_dict(row) for row in state.get("checks", [])]

    # Always include a typed receipt outcome; missing evidence remains UNKNOWN.
    if not checks:
        checks = [
            QualificationCheck(
                "qualification-evidence",
                CheckStatus.UNKNOWN,
                (_evidence_ref("missing", subject_digest(subject)),),
            )
        ]
    receipt = create_qualification_receipt(subject, graph_version, status, checks)
    return {"receipt": receipt.to_dict(), "receipt_ref": receipt.receipt_id}


def build_qualification_graph(
    source: ReadOnlyProjectionSource,
    receipt_store: QualificationReceiptWriter,
    graph_version: str = GRAPH_VERSION,
    *,
    checkpointer: Any,
):
    """Compile the qualification graph with an explicitly supplied checkpointer.

    The source and receipt store are injected into node closures, never serialized
    into graph state. The checkpointer is mandatory; callers that need persistent
    execution use ``open_qualification_runtime`` below.
    """
    if not LANGGRAPH_AVAILABLE:
        raise LangGraphUnavailable("Install the optional 'qualification' extra to run LangGraph")
    if checkpointer is None:
        raise ValueError("a persistent LangGraph checkpointer is required")
    if not callable(getattr(source, "read_prefix", None)):
        raise TypeError("source must implement the read-only read_prefix(subject) contract")
    if not callable(getattr(receipt_store, "put_idempotent", None)):
        raise TypeError("receipt_store must implement put_idempotent(receipt)")
    if not graph_version:
        raise ValueError("graph_version is required")

    def bind_subject(state: QualificationGraphState, config: RunnableConfig) -> dict[str, Any]:
        subject = QualificationSubject.from_dict(state["subject"])
        execution = QualificationExecution.from_dict(state["execution"])
        if execution.graph_version != graph_version:
            raise QualificationInputError("execution graph_version does not match compiled graph")
        if execution.subject_digest != subject_digest(subject):
            raise QualificationInputError("execution subject_digest does not match subject")
        if execution.qualification_id != create_qualification_id(subject, graph_version):
            raise QualificationInputError("qualification_id does not match subject and graph_version")
        configured_thread = config.get("configurable", {}).get("thread_id")
        if configured_thread != execution.langgraph_thread_id.value:
            raise QualificationInputError("LangGraph config thread_id does not match LangGraphThreadId")
        check = QualificationCheck(
            "identity-binding",
            CheckStatus.PASS,
            (_evidence_ref("subject", execution.subject_digest),),
        )
        return {
            "subject": subject.to_dict(),
            "execution": execution.to_dict(),
            "graph_version": graph_version,
            "terminal_status": None,
            **_append_check({}, check),
        }

    def load_boundary(state: QualificationGraphState) -> dict[str, Any]:
        if _terminal(state):
            return {}
        subject = QualificationSubject.from_dict(state["subject"])
        try:
            prefix = source.read_prefix(subject)
        except ProjectionSourceUnavailable:
            check = QualificationCheck(
                "durable-prefix",
                CheckStatus.UNKNOWN,
                (_evidence_ref("source-unavailable", subject_digest(subject)),),
            )
            return {
                "terminal_status": QualificationStatus.UNKNOWN.value,
                "error_code": "PROJECTION_SOURCE_UNAVAILABLE",
                **_append_check(state, check),
            }
        binding = validate_prefix_binding(prefix, subject)
        check = QualificationCheck(
            "subject-current",
            binding.status,
            binding.evidence_refs,
        )
        if binding.status is not CheckStatus.PASS:
            terminal_status = (
                QualificationStatus.DRIFTED.value
                if binding.status is CheckStatus.DRIFTED
                else QualificationStatus.UNKNOWN.value
            )
            return {
                "terminal_status": terminal_status,
                "history_digest": prefix.history_digest,
                "semantic_facts_digest": prefix.semantic_facts_digest,
                "event_count": prefix.event_count,
                **_append_check(state, check),
            }
        return {
            "history_digest": prefix.history_digest,
            "semantic_facts_digest": prefix.semantic_facts_digest,
            "event_count": prefix.event_count,
            **_append_check(state, check),
        }

    def reduce_prefix(state: QualificationGraphState) -> dict[str, Any]:
        if _terminal(state):
            return {}
        subject = QualificationSubject.from_dict(state["subject"])
        prefix, drift = _prefix_or_drift(
            source,
            subject,
            state.get("history_digest"),
            state.get("semantic_facts_digest"),
        )
        if prefix is None or drift is not None:
            check = QualificationCheck(
                "history-boundary-stable",
                CheckStatus.DRIFTED if drift else CheckStatus.UNKNOWN,
                (_evidence_ref("boundary-drift", state.get("history_digest", subject_digest(subject))),),
            )
            return {
                "terminal_status": QualificationStatus.DRIFTED.value if drift else QualificationStatus.UNKNOWN.value,
                "error_code": drift or "PROJECTION_SOURCE_UNAVAILABLE",
                **_append_check(state, check),
            }
        projection = reduce_events(prefix.events)
        if projection.run_id != subject.dwo_run_id.value:
            check = QualificationCheck(
                "reducer-run-identity",
                CheckStatus.FAIL,
                (_evidence_ref("projection", prefix.history_digest),),
            )
            return {
                "terminal_status": QualificationStatus.FAILED.value,
                "projection_digest": _canonical_digest(projection.to_dict()),
                **_append_check(state, check),
            }
        digest = _canonical_digest(projection.to_dict())
        anomaly_status = CheckStatus.FAIL if projection.anomalies else CheckStatus.PASS
        anomaly_refs = (
            _evidence_ref("anomalies", digest),
        ) if projection.anomalies else (_evidence_ref("projection", digest),)
        anomaly_check = QualificationCheck("projection-anomalies", anomaly_status, anomaly_refs)
        identity_check = QualificationCheck(
            "reducer-run-identity",
            CheckStatus.PASS,
            (_evidence_ref("projection", digest),),
        )
        terminal = QualificationStatus.FAILED.value if projection.anomalies else None
        return {
            "projection_digest": digest,
            "terminal_status": terminal,
            **_append_check({**state, **_append_check(state, identity_check)}, anomaly_check),
        }

    def replay_prefix(state: QualificationGraphState) -> dict[str, Any]:
        if _terminal(state):
            return {}
        subject = QualificationSubject.from_dict(state["subject"])
        prefix, drift = _prefix_or_drift(
            source,
            subject,
            state.get("history_digest"),
            state.get("semantic_facts_digest"),
        )
        if prefix is None or drift is not None:
            check = QualificationCheck(
                "replay-boundary-stable",
                CheckStatus.DRIFTED if drift else CheckStatus.UNKNOWN,
                (_evidence_ref("replay-boundary", state.get("history_digest", subject_digest(subject))),),
            )
            return {
                "terminal_status": QualificationStatus.DRIFTED.value if drift else QualificationStatus.UNKNOWN.value,
                "error_code": drift or "PROJECTION_SOURCE_UNAVAILABLE",
                **_append_check(state, check),
            }
        timeline = ReplayTimeline(prefix.events)
        replay_projection = timeline.tip().projection
        replay_digest = timeline.replay_digest()
        parity = _canonical_digest(replay_projection.to_dict()) == state.get("projection_digest")
        deterministic = timeline.verify_determinism(repeats=3)
        parity_check = QualificationCheck(
            "reducer-replay-parity",
            CheckStatus.PASS if parity else CheckStatus.FAIL,
            (_evidence_ref("replay", replay_digest),),
        )
        deterministic_check = QualificationCheck(
            "replay-determinism",
            CheckStatus.PASS if deterministic else CheckStatus.FAIL,
            (_evidence_ref("replay", replay_digest),),
        )
        new_state = {**state, **_append_check(state, parity_check)}
        new_state.update(_append_check(new_state, deterministic_check))
        terminal = None if parity and deterministic else QualificationStatus.FAILED.value
        return {"replay_digest": replay_digest, "terminal_status": terminal, **new_state}

    def semantic_qualification(state: QualificationGraphState) -> dict[str, Any]:
        if _terminal(state):
            return {}
        subject = QualificationSubject.from_dict(state["subject"])
        prefix, drift = _prefix_or_drift(
            source,
            subject,
            state.get("history_digest"),
            state.get("semantic_facts_digest"),
        )
        if prefix is None or drift is not None:
            check = QualificationCheck(
                "semantic-evidence-current",
                CheckStatus.DRIFTED if drift else CheckStatus.UNKNOWN,
                (_evidence_ref("semantic-evidence", state.get("history_digest", subject_digest(subject))),),
            )
            return {
                "terminal_status": QualificationStatus.DRIFTED.value if drift else QualificationStatus.UNKNOWN.value,
                "error_code": drift or "PROJECTION_SOURCE_UNAVAILABLE",
                **_append_check(state, check),
            }
        verified = verify_semantic_evidence(prefix.semantic_evidence, subject, prefix)
        new_state: dict[str, Any] = dict(state)
        for check in verified:
            new_state.update(_append_check(new_state, check))
        return new_state

    def build_receipt(state: QualificationGraphState) -> dict[str, Any]:
        return _make_graph_receipt(state, graph_version)

    def persist_receipt(state: QualificationGraphState) -> dict[str, Any]:
        receipt_data = state.get("receipt")
        if receipt_data is None:
            raise ValueError("receipt must be built before persistence")
        receipt = receipt_store.put_idempotent(QualificationReceipt.from_dict(receipt_data))
        execution = QualificationExecution.from_dict(state["execution"])
        execution_status = {
            QualificationStatus.QUALIFIED: ExecutionStatus.PASSED,
            QualificationStatus.FAILED: ExecutionStatus.FAILED,
            QualificationStatus.DRIFTED: ExecutionStatus.DRIFTED,
            QualificationStatus.UNKNOWN: ExecutionStatus.UNKNOWN,
        }[receipt.status]
        completed = QualificationExecution(
            qualification_id=execution.qualification_id,
            subject_digest=execution.subject_digest,
            langgraph_thread_id=execution.langgraph_thread_id,
            graph_version=execution.graph_version,
            status=execution_status,
            evidence_refs=receipt.evidence_refs,
            receipt_ref=receipt.receipt_id,
        )
        return {
            "receipt": receipt.to_dict(),
            "receipt_ref": receipt.receipt_id,
            "execution": completed.to_dict(),
            "terminal_status": receipt.status.value,
        }

    workflow = _StateGraph(QualificationGraphState)
    workflow.add_node("bind_subject", bind_subject)
    workflow.add_node("load_durable_prefix", load_boundary)
    workflow.add_node("pure_reduce", reduce_prefix)
    workflow.add_node("replay_parity", replay_prefix)
    workflow.add_node("semantic_qualification", semantic_qualification)
    workflow.add_node("build_immutable_receipt", build_receipt)
    workflow.add_node("persist_receipt_idempotently", persist_receipt)
    workflow.add_edge(_START, "bind_subject")
    workflow.add_edge("bind_subject", "load_durable_prefix")
    workflow.add_edge("load_durable_prefix", "pure_reduce")
    workflow.add_edge("pure_reduce", "replay_parity")
    workflow.add_edge("replay_parity", "semantic_qualification")
    workflow.add_edge("semantic_qualification", "build_immutable_receipt")
    workflow.add_edge("build_immutable_receipt", "persist_receipt_idempotently")
    workflow.add_edge("persist_receipt_idempotently", _END)
    return workflow.compile(checkpointer=checkpointer)


@contextmanager
def open_qualification_runtime(
    source: ReadOnlyProjectionSource,
    checkpoint_path: str | Path,
    receipt_path: str | Path,
    projection_events_path: str | Path,
    graph_version: str = GRAPH_VERSION,
) -> Iterator[tuple[Any, SQLiteQualificationReceiptStore]]:
    """Open separate SQLite stores for operational checkpoints and receipts."""
    if not LANGGRAPH_AVAILABLE:
        raise LangGraphUnavailable("Install the optional 'qualification' extra to run LangGraph")
    assert_storage_isolation(checkpoint_path, receipt_path, projection_events_path)
    with _SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        checkpointer.setup()
        with SQLiteQualificationReceiptStore(receipt_path) as receipt_store:
            graph = build_qualification_graph(source, receipt_store, graph_version, checkpointer=checkpointer)
            yield graph, receipt_store
