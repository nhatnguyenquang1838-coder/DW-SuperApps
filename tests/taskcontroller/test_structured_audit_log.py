from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.facade import AuditFacade
from taskcontroller.audit.structured_log import StructuredAuditFormatter


def _event() -> AuditEvent:
    return AuditEvent(
        event_id="evt-structured-1",
        timestamp="2026-08-17T05:30:00Z",
        run_id="run-structured-1",
        source="test.source",
        decision_kind="TEST_DECISION",
        node_id="node-1",
        authority_ref="auth-1",
        payload_summary="bounded semantic summary",
        raw_payload_ref="github://example/ref",
        sequence=7,
        before={"secret": "must-not-log"},
        after={"large": "must-not-log"},
        annotations={"internal": "must-not-log"},
    )


def test_structured_formatter_allows_only_bounded_metadata() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredAuditFormatter())
    logger = logging.getLogger("taskcontroller.audit.structured-test")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    event = _event()
    logger.info(
        event.payload_summary,
        extra={
            "event_id": event.event_id,
            "run_id": event.run_id,
            "source": event.source,
            "decision_kind": event.decision_kind,
            "node_id": event.node_id,
            "authority_ref": event.authority_ref,
            "raw_payload_ref": event.raw_payload_ref,
            "sequence": event.sequence,
        },
    )
    record = json.loads(stream.getvalue())
    assert record["event_id"] == event.event_id
    assert record["run_id"] == event.run_id
    assert record["sequence"] == 7
    assert record["message"] == "bounded semantic summary"
    serialized = json.dumps(record, sort_keys=True)
    assert "must-not-log" not in serialized
    assert "before" not in record
    assert "after" not in record
    assert "annotations" not in record


def test_audit_facade_optionally_projects_record_to_structured_logger(tmp_path: Path) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredAuditFormatter())
    logger = logging.getLogger("taskcontroller.audit.facade-test")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    facade = AuditFacade(tmp_path / "audit.db", logger=logger)
    try:
        event = _event()
        revision = facade.record(event.run_id, event)
        assert revision == 1
        persisted = facade.events(event.run_id)
        assert [item.event_id for item in persisted] == [event.event_id]
        record = json.loads(stream.getvalue())
        assert record["event_id"] == event.event_id
        assert record["run_id"] == event.run_id
        assert record["decision_kind"] == event.decision_kind
    finally:
        facade.close()
