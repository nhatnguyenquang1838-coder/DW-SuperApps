"""TDD: structured log emission + log rotation for FileAuditWriter."""
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.writer import FileAuditWriter
from taskcontroller.audit.structured_log import StructuredFormatter


def _event(run_id: str = "run.1", **overrides) -> AuditEvent:
    kwargs: dict = {
        "event_id": "evt-test",
        "timestamp": "2026-08-16T00:00:00Z",
        "run_id": run_id,
        "source": "test.source",
        "decision_kind": "TEST",
    }
    kwargs.update(overrides)
    return AuditEvent(**kwargs)


class StructuredLogEmissionTests(unittest.TestCase):
    """Red → green: FileAuditWriter.emit() must also emit a structured JSON log record."""

    def test_emit_logs_structured_json(self) -> None:
        """Each emit() produces a JSON log record with timestamp, level, logger, message."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            writer = FileAuditWriter(log_path)

            stream = io.StringIO()
            handler = logging.StreamHandler(stream)
            handler.setFormatter(StructuredFormatter())
            logger = logging.getLogger("taskcontroller.audit.writer")
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False

            event = _event()
            writer.emit(event)

            output = stream.getvalue().strip()
            record = json.loads(output)

            self.assertIn("timestamp", record)
            self.assertIn("level", record)
            self.assertEqual(record["level"], "INFO")
            self.assertIn("logger", record)
            self.assertEqual(record["logger"], "taskcontroller.audit.writer")
            self.assertIn("message", record)
            self.assertIn("run_id", record)
            self.assertEqual(record["run_id"], "run.1")
            self.assertIn("source", record)
            self.assertEqual(record["source"], "test.source")
            self.assertIn("decision_kind", record)
            self.assertEqual(record["decision_kind"], "TEST")

            logger.removeHandler(handler)

    def test_emit_log_has_authority_ref(self) -> None:
        """Structured log records carry authority_ref when the event has one."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            writer = FileAuditWriter(log_path)

            stream = io.StringIO()
            handler = logging.StreamHandler(stream)
            handler.setFormatter(StructuredFormatter())
            logger = logging.getLogger("taskcontroller.audit.writer")
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False

            event = _event(authority_ref="auth-abc")
            writer.emit(event)

            output = stream.getvalue().strip()
            record = json.loads(output)

            self.assertEqual(record["authority_ref"], "auth-abc")

            logger.removeHandler(handler)


class LogRotationTests(unittest.TestCase):
    """Red → green: FileAuditWriter rotates log file when MAX_SIZE is exceeded."""

    def test_rotation_creates_backup(self) -> None:
        """When file size exceeds max_size, the current file is moved to .1 backup."""
        max_size = 50  # smaller than one event line (~300+ bytes)

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            writer = FileAuditWriter(log_path, max_size=max_size)

            big_event = _event(payload_summary="x" * 100)
            for _ in range(5):
                writer.emit(big_event)

            # Backup .1 must exist (at least one rotation occurred)
            backup = Path(tmp) / "audit.jsonl.1"
            self.assertTrue(backup.exists(), f"Expected backup {backup} to exist")

            # After rotation, current file has only the last event (one line)
            lines = log_path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 1, "Current file should have exactly 1 event after rotation")

    def test_rotation_keep_last_n(self) -> None:
        """Only the last N backups are kept (default 5)."""
        max_size = 50  # triggers rotation on every emit

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            writer = FileAuditWriter(log_path, max_size=max_size, backup_count=2)

            for i in range(20):
                writer.emit(_event(event_id=f"evt-{i}", payload_summary="x" * 100))

            # Should have at most backup_count numbered backups
            backups = sorted(Path(tmp).glob("audit.jsonl.*"))
            numbered = [b for b in backups if b.name != log_path.name]
            self.assertLessEqual(len(numbered), 2,
                                 f"Expected at most 2 backups, got {len(numbered)}: {[b.name for b in numbered]}")

    def test_no_rotation_below_threshold(self) -> None:
        """When file stays below max_size, no backup is created."""
        max_size = 10 * 1024 * 1024  # 10MB default

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            writer = FileAuditWriter(log_path, max_size=max_size)

            for i in range(5):
                writer.emit(_event(event_id=f"evt-{i}"))

            backup = Path(tmp) / "audit.jsonl.1"
            self.assertFalse(backup.exists(), "No rotation should occur below threshold")
            # All 5 events in current file
            lines = log_path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 5)
