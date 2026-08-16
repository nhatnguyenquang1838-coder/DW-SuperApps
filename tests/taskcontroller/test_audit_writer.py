import json
import tempfile
import unittest
from pathlib import Path

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.writer import FileAuditWriter, CheckpointAuditWriter


def _event(rev: int = 1) -> AuditEvent:
    return AuditEvent(
        event_id=f"evt-{rev}",
        timestamp="2026-08-16T00:00:00Z",
        run_id="run.1",
        source="test.source",
        decision_kind="TEST",
    )


class FileAuditWriterTests(unittest.TestCase):
    def test_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            w = FileAuditWriter(path)
            w.emit(_event(1))
            w.emit(_event(2))
            lines = path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 2)
            self.assertIn("evt-1", lines[0])
            self.assertIn("evt-2", lines[1])

    def test_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            w = FileAuditWriter(path)
            w.emit(_event(1))
            w.emit(_event(2))
            events = w.replay()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0].event_id, "evt-1")
            self.assertEqual(events[1].event_id, "evt-2")

    def test_empty_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            w = FileAuditWriter(Path(tmp) / "nonexistent.jsonl")
            self.assertEqual(w.replay(), [])


class CheckpointAuditWriterTests(unittest.TestCase):
    def test_cas_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            w = CheckpointAuditWriter(path)
            rev1 = w.emit(_event(1), expected_revision=0)
            self.assertEqual(rev1, 1)
            rev2 = w.emit(_event(2), expected_revision=1)
            self.assertEqual(rev2, 2)

    def test_cas_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            w = CheckpointAuditWriter(path)
            w.emit(_event(1), expected_revision=0)
            with self.assertRaises(ValueError) as ctx:
                w.emit(_event(2), expected_revision=5)
            self.assertIn("CAS_MISMATCH", str(ctx.exception))

    def test_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            w = CheckpointAuditWriter(path)
            w.emit(_event(1))
            w.emit(_event(2))
            events = w.replay()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_id"], "evt-1")

    def test_store_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            w = CheckpointAuditWriter(path)
            w.emit(_event(1))
            digest = w.store_digest()
            self.assertTrue(digest.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
