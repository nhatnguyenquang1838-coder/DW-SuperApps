import json
import unittest
from taskcontroller.audit.event import AuditEvent


class AuditEventTests(unittest.TestCase):
    def _sample(self) -> AuditEvent:
        return AuditEvent(
            event_id="evt-1",
            timestamp="2026-08-16T00:00:00Z",
            run_id="run.1",
            source="test.source",
            decision_kind="TEST",
        )

    def test_round_trip(self) -> None:
        e = self._sample()
        restored = AuditEvent.from_json(e.to_json())
        self.assertEqual(restored, e)

    def test_from_dict(self) -> None:
        e = self._sample()
        restored = AuditEvent.from_dict(e.to_dict())
        self.assertEqual(restored.event_id, "evt-1")

    def test_required_fields(self) -> None:
        with self.assertRaises(ValueError):
            AuditEvent(event_id="", timestamp="t", run_id="r", source="s", decision_kind="d")
        with self.assertRaises(ValueError):
            AuditEvent(event_id="e", timestamp="", run_id="r", source="s", decision_kind="d")
        with self.assertRaises(ValueError):
            AuditEvent(event_id="e", timestamp="t", run_id="", source="s", decision_kind="d")
        with self.assertRaises(ValueError):
            AuditEvent(event_id="e", timestamp="t", run_id="r", source="", decision_kind="d")
        with self.assertRaises(ValueError):
            AuditEvent(event_id="e", timestamp="t", run_id="r", source="s", decision_kind="")

    def test_payload_summary_truncation(self) -> None:
        with self.assertRaises(ValueError):
            AuditEvent(
                event_id="e", timestamp="t", run_id="r", source="s", decision_kind="d",
                payload_summary="x" * 301,
            )


if __name__ == "__main__":
    unittest.main()
