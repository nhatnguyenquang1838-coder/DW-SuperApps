"""TC-MBX-901: bounded semantic audit event contract."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.facade import AuditFacade, NoOpAuditFacade
from taskcontroller.audit.semantic_events import (
    SemanticAuditError,
    SemanticAuditEventKind,
    SemanticAuditEventRecorder,
    reconstruct_semantic_timeline,
)


EXPECTED_KINDS = (
    "MAILBOX_WRITE",
    "MAILBOX_READBACK",
    "WAKEUP",
    "BOOTSTRAP",
    "CLASSIFICATION",
    "FANOUT",
    "CHILD_COMPLETION",
    "MIXER",
    "TERMINAL_COMMIT",
    "RESUME",
    "STALE_REJECTION",
)


def _record_all(recorder: SemanticAuditEventRecorder) -> None:
    for ordinal, kind in enumerate(SemanticAuditEventKind, start=1):
        recorder.record(
            kind,
            event_id=f"evt-{ordinal:02d}",
            timestamp=f"2026-09-12T00:00:{ordinal:02d}Z",
            run_id="run-901",
            source="controller",
            node_id="node-root",
            actor="controller",
            authority_ref="artifact://authority/tc-901",
            evidence_refs=(f"artifact://evidence/{ordinal}",),
            metadata={
                "status": "accepted",
                "sequence_hint": ordinal,
                "correlation_id": "corr-901",
            },
        )


def test_catalog_contains_all_required_semantic_stages() -> None:
    assert tuple(kind.value for kind in SemanticAuditEventKind) == EXPECTED_KINDS


def test_recording_uses_existing_facade_and_keeps_payload_bounded(tmp_path) -> None:
    facade = AuditFacade(tmp_path / "audit.sqlite3")
    try:
        recorder = SemanticAuditEventRecorder(facade)
        _record_all(recorder)
        events = facade.events("run-901")

        assert len(events) == len(EXPECTED_KINDS)
        assert [event.sequence for event in events] == list(range(1, 12))
        assert [event.decision_kind for event in events] == list(EXPECTED_KINDS)
        assert all(event.payload_summary in EXPECTED_KINDS for event in events)
        assert all(event.raw_payload_ref == "" for event in events)
        assert all(event.after["semantic_event"] == event.decision_kind for event in events)
        assert all("prompt" not in json.dumps(event.to_dict()).lower() for event in events)
    finally:
        facade.close()


def test_timeline_reconstructs_order_and_evidence_without_transcript(tmp_path) -> None:
    facade = AuditFacade(tmp_path / "audit.sqlite3")
    try:
        _record_all(SemanticAuditEventRecorder(facade))
        timeline = reconstruct_semantic_timeline(facade, "run-901")

        assert timeline.run_id == "run-901"
        assert timeline.event_count == 11
        assert [entry.kind.value for entry in timeline.entries] == list(EXPECTED_KINDS)
        assert [entry.sequence for entry in timeline.entries] == list(range(1, 12))
        assert timeline.evidence_refs == tuple(
            f"artifact://evidence/{ordinal}" for ordinal in range(1, 12)
        )
        serialized = json.dumps(timeline.to_dict(), sort_keys=True)
        assert "prompt" not in serialized.lower()
        assert "transcript" not in serialized.lower()
        assert "chain-of-thought" not in serialized.lower()
    finally:
        facade.close()


def test_timeline_sorting_prefers_ledger_sequence_over_timestamp(tmp_path) -> None:
    facade = AuditFacade(tmp_path / "audit.sqlite3")
    try:
        recorder = SemanticAuditEventRecorder(facade)
        recorder.record(
            SemanticAuditEventKind.RESUME,
            event_id="evt-2",
            timestamp="2026-09-12T00:00:01Z",
            run_id="run-sort",
            source="controller",
            evidence_refs=("artifact://evidence/2",),
        )
        recorder.record(
            SemanticAuditEventKind.BOOTSTRAP,
            event_id="evt-1",
            timestamp="2026-09-12T00:00:00Z",
            run_id="run-sort",
            source="executor",
            evidence_refs=("artifact://evidence/1",),
        )
        timeline = reconstruct_semantic_timeline(facade, "run-sort")
        assert [entry.kind for entry in timeline.entries] == [
            SemanticAuditEventKind.RESUME,
            SemanticAuditEventKind.BOOTSTRAP,
        ]
    finally:
        facade.close()


def test_noop_facade_preserves_compatibility() -> None:
    recorder = SemanticAuditEventRecorder(NoOpAuditFacade())
    assert (
        recorder.record(
            SemanticAuditEventKind.BOOTSTRAP,
            event_id="evt-noop",
            timestamp="2026-09-12T00:00:00Z",
            run_id="run-noop",
            source="executor",
        )
        == 0
    )
    assert reconstruct_semantic_timeline(NoOpAuditFacade(), "run-noop").event_count == 0


@pytest.mark.parametrize(
    ("kind", "metadata"),
    [
        ("UNKNOWN", {}),
        ("PROMPT", {}),
        (SemanticAuditEventKind.BOOTSTRAP, {"prompt": "secret"}),
        (SemanticAuditEventKind.BOOTSTRAP, {"transcript": "secret"}),
        (SemanticAuditEventKind.BOOTSTRAP, {"unbounded_field": "value"}),
    ],
)
def test_rejects_unknown_or_unbounded_semantic_payload(kind, metadata: Mapping) -> None:
    recorder = SemanticAuditEventRecorder(NoOpAuditFacade())
    with pytest.raises(SemanticAuditError):
        recorder.record(
            kind,
            event_id="evt-invalid",
            timestamp="2026-09-12T00:00:00Z",
            run_id="run-invalid",
            source="controller",
            metadata=metadata,
        )


def test_rejects_malformed_evidence_refs() -> None:
    recorder = SemanticAuditEventRecorder(NoOpAuditFacade())
    with pytest.raises(SemanticAuditError, match="EVIDENCE_REF_INVALID"):
        recorder.record(
            SemanticAuditEventKind.STALE_REJECTION,
            event_id="evt-invalid-ref",
            timestamp="2026-09-12T00:00:00Z",
            run_id="run-invalid",
            source="controller",
            evidence_refs=("raw prompt text",),
        )


def test_rejects_missing_required_identity() -> None:
    recorder = SemanticAuditEventRecorder(NoOpAuditFacade())
    with pytest.raises(SemanticAuditError, match="IDENTITY_REQUIRED"):
        recorder.record(
            SemanticAuditEventKind.MAILBOX_WRITE,
            event_id="",
            timestamp="2026-09-12T00:00:00Z",
            run_id="run-invalid",
            source="controller",
        )


def test_reconstruction_rejects_foreign_run_events() -> None:
    foreign_event = AuditEvent(
        event_id="evt-foreign",
        timestamp="2026-09-12T00:00:00Z",
        run_id="run-other",
        source="executor",
        decision_kind=SemanticAuditEventKind.BOOTSTRAP.value,
        payload_summary=SemanticAuditEventKind.BOOTSTRAP.value,
        after={"semantic_event": SemanticAuditEventKind.BOOTSTRAP.value},
    )

    class ForeignEventSource:
        def events(self, run_id: str) -> list[AuditEvent]:
            return [foreign_event]

    with pytest.raises(SemanticAuditError, match="RUN_ID_MISMATCH"):
        reconstruct_semantic_timeline(ForeignEventSource(), "run-901")


def test_reconstruction_ignores_nonsemantic_legacy_events(tmp_path) -> None:
    facade = AuditFacade(tmp_path / "audit.sqlite3")
    try:
        facade.record(
            "run-legacy",
            AuditEvent(
                event_id="legacy-1",
                timestamp="2026-09-12T00:00:00Z",
                run_id="run-legacy",
                source="controller",
                decision_kind="ROOT_CREATE",
                payload_summary="root-created",
            ),
        )
        timeline = reconstruct_semantic_timeline(facade, "run-legacy")
        assert timeline.event_count == 0
    finally:
        facade.close()
