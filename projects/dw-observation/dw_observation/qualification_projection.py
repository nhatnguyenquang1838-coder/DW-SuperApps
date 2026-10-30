"""Read-only projection of qualification receipts for UI/API consumers.

This boundary never opens a LangGraph checkpointer and never writes receipts or
canonical DWO history. Current-source identity comes from a host-provided
read-only reader; progress, when available, comes from a separate read-only
provider rather than checkpoint history.
"""
from __future__ import annotations

from typing import Any, Protocol

from .qualification_models import (
    DwoRunId,
    ExecutionStatus,
    QualificationReceipt,
    QualificationStatus,
    QualificationSubject,
    subject_digest,
)
from .qualification_store import SQLiteQualificationReceiptStore

PROJECTION_SCHEMA_VERSION = "dwo.qualification-projection/1"
UI_QUALIFICATION_STATUSES = ("UNKNOWN", "QUALIFYING", "QUALIFIED", "FAILED", "DRIFTED")


class CurrentSubjectReader(Protocol):
    """Resolve the current exact source binding without mutating DWO state."""

    def read_current_subject(self, run_id: DwoRunId) -> QualificationSubject | None: ...


class QualificationProgressReader(Protocol):
    """Optional read-only progress source; must not expose LangGraph checkpoints."""

    def read_status(
        self,
        run_id: DwoRunId,
        current_subject_digest: str,
    ) -> ExecutionStatus | None: ...


def _status_for_progress(status: ExecutionStatus | None) -> str | None:
    if status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING, ExecutionStatus.INTERRUPTED):
        return "QUALIFYING"
    if status is ExecutionStatus.FAILED:
        return "FAILED"
    if status is ExecutionStatus.DRIFTED:
        return "DRIFTED"
    return None


def _projection(
    *,
    run_id: DwoRunId,
    status: str,
    current_subject: QualificationSubject | None,
    receipt: QualificationReceipt | None = None,
    receipt_subject_digest: str | None = None,
    reason_code: str,
) -> dict[str, Any]:
    digest = subject_digest(current_subject) if current_subject is not None else None
    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "run_id": run_id.value,
        "status": status,
        "subject_digest": digest,
        "current_subject_digest": digest,
        "receipt_subject_digest": receipt_subject_digest or (receipt.subject_digest if receipt else None),
        "receipt_id": receipt.receipt_id if receipt else None,
        "graph_version": receipt.graph_version if receipt else None,
        "source_repository": current_subject.source_repository if current_subject else None,
        "source_sha": current_subject.source_sha if current_subject else None,
        "durable_position": current_subject.durable_position if current_subject else None,
        "evidence_refs": list(receipt.evidence_refs) if receipt else [],
        "authority_granted": False,
        "projection_events_mutated": False,
        "reason_code": reason_code,
    }


class QualificationProjectionService:
    """Build a current-subject projection from read-only sources and receipts."""

    def __init__(
        self,
        receipt_store: SQLiteQualificationReceiptStore,
        current_subject_reader: CurrentSubjectReader,
        *,
        graph_version: str,
        progress_reader: QualificationProgressReader | None = None,
    ) -> None:
        if getattr(receipt_store, "read_only", None) is not True:
            raise ValueError("qualification projection requires a read-only receipt store")
        if not graph_version or not graph_version.strip():
            raise ValueError("graph_version is required")
        self._receipt_store = receipt_store
        self._subject_reader = current_subject_reader
        self._progress_reader = progress_reader
        self._graph_version = graph_version

    def read(self, run_id: DwoRunId | str) -> dict[str, Any]:
        typed_run_id = run_id if isinstance(run_id, DwoRunId) else DwoRunId(run_id)
        current_subject = self._subject_reader.read_current_subject(typed_run_id)
        if current_subject is not None and current_subject.dwo_run_id != typed_run_id:
            raise ValueError("current subject reader returned another DWO run identity")
        receipts = self._receipt_store.get_for_run(typed_run_id)
        if current_subject is None:
            return _projection(
                run_id=typed_run_id,
                status="UNKNOWN",
                current_subject=None,
                reason_code="CURRENT_SUBJECT_UNAVAILABLE",
            )

        current_digest = subject_digest(current_subject)
        exact = [
            receipt
            for receipt in receipts
            if receipt.subject_digest == current_digest and receipt.graph_version == self._graph_version
        ]
        if len(exact) == 1:
            receipt = exact[0]
            if receipt.authority_granted or receipt.projection_events_mutated:
                return _projection(
                    run_id=typed_run_id,
                    status="UNKNOWN",
                    current_subject=current_subject,
                    receipt_subject_digest=receipt.subject_digest,
                    reason_code="RECEIPT_EFFECT_CONTRACT_VIOLATION",
                )
            return _projection(
                run_id=typed_run_id,
                status=receipt.status.value,
                current_subject=current_subject,
                receipt=receipt,
                reason_code="MATCHED_IMMUTABLE_RECEIPT",
            )
        if len(exact) > 1:
            return _projection(
                run_id=typed_run_id,
                status="UNKNOWN",
                current_subject=current_subject,
                reason_code="AMBIGUOUS_MATCHING_RECEIPTS",
            )

        progress_status = (
            self._progress_reader.read_status(typed_run_id, current_digest)
            if self._progress_reader is not None
            else None
        )
        progress_projection = _status_for_progress(progress_status)
        if progress_projection is not None:
            return _projection(
                run_id=typed_run_id,
                status=progress_projection,
                current_subject=current_subject,
                reason_code="READ_ONLY_PROGRESS",
            )
        if receipts:
            stale_digest = sorted(receipt.subject_digest for receipt in receipts)[-1]
            return _projection(
                run_id=typed_run_id,
                status="DRIFTED",
                current_subject=current_subject,
                receipt_subject_digest=stale_digest,
                reason_code="SUBJECT_OR_GRAPH_VERSION_DRIFT",
            )
        return _projection(
            run_id=typed_run_id,
            status="UNKNOWN",
            current_subject=current_subject,
            reason_code="NO_IMMUTABLE_RECEIPT",
        )
