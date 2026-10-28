"""Read-only projection-prefix contract tests for qualification."""
from __future__ import annotations

import unittest

from dw_observation.events import RunProjectionEvent
from dw_observation.qualification_models import (
    CheckStatus,
    DwoRunId,
    QualificationCheck,
    QualificationSubject,
    TaskRef,
)
from dw_observation.qualification_sources import ProjectionPrefix, validate_prefix_binding


def event(run_id: str = "DWO-RUN-SOURCE", sequence: int = 0, event_id: str | None = None):
    return RunProjectionEvent(
        occurred_at=f"2026-10-28T00:00:{sequence:02d}Z",
        run_id=run_id,
        source_event_id=event_id or f"evt-{sequence}",
        source_system="taskcontroller",
        source_digest=f"sha256:event-{sequence}",
        sequence=sequence,
        event_type="run_started" if sequence == 0 else "node_progress",
        node_id="node-1" if sequence else None,
    )


def subject() -> QualificationSubject:
    return QualificationSubject(
        dwo_run_id=DwoRunId("DWO-RUN-SOURCE"),
        task_ref=TaskRef("SCRUM-820"),
        source_repository="owner/gwc",
        source_sha="a" * 40,
        lifecycle_profile="gwc.universal-run/1",
        projection_contract_version="dwo.projection-contract/2",
        reducer_version="dwo.reducer/1",
        durable_position="projection_ordinal=1",
    )


def prefix(**overrides) -> ProjectionPrefix:
    values = {
        "dwo_run_id": DwoRunId("DWO-RUN-SOURCE"),
        "source_repository": "owner/gwc",
        "source_sha": "a" * 40,
        "lifecycle_profile": "gwc.universal-run/1",
        "projection_contract_version": "dwo.projection-contract/2",
        "reducer_version": "dwo.reducer/1",
        "durable_position": "projection_ordinal=1",
        "events": (event(),),
        "semantic_checks": (
            QualificationCheck("hierarchy", CheckStatus.PASS, ("evidence://hierarchy/1",)),
        ),
    }
    values.update(overrides)
    return ProjectionPrefix(**values)


class ProjectionPrefixTests(unittest.TestCase):
    def test_prefix_binds_exact_subject_and_position(self):
        result = validate_prefix_binding(prefix(), subject())
        self.assertTrue(result.current)
        self.assertEqual(result.status, CheckStatus.PASS)
        self.assertTrue(result.evidence_refs)

    def test_source_sha_or_durable_position_drift_is_detected(self):
        drifted_sha = validate_prefix_binding(prefix(source_sha="b" * 40), subject())
        drifted_position = validate_prefix_binding(prefix(durable_position="projection_ordinal=2"), subject())
        self.assertEqual(drifted_sha.status, CheckStatus.DRIFTED)
        self.assertEqual(drifted_position.status, CheckStatus.DRIFTED)

    def test_history_digest_is_deterministic_and_binds_event_order_and_boundary(self):
        first = prefix()
        second = prefix()
        reordered = prefix(events=(event(sequence=1), event(sequence=0)))
        next_position = prefix(durable_position="projection_ordinal=2")
        self.assertEqual(first.history_digest, second.history_digest)
        self.assertNotEqual(first.history_digest, reordered.history_digest)
        self.assertNotEqual(first.history_digest, next_position.history_digest)

    def test_prefix_rejects_events_from_another_dwo_run(self):
        with self.assertRaises(ValueError):
            prefix(events=(event(run_id="OTHER-RUN"),))

    def test_projection_events_cannot_claim_writable_capability(self):
        with self.assertRaises(ValueError):
            RunProjectionEvent(
                occurred_at="2026-10-28T00:00:00Z",
                run_id="DWO-RUN-SOURCE",
                source_event_id="evt-0",
                source_system="taskcontroller",
                source_digest="sha256:event-0",
                event_type="run_started",
                read_only_projection=False,
            )


if __name__ == "__main__":
    unittest.main()
