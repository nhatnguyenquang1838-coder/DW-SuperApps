"""M3 tests — deterministic replay, synchronized rewind, LIVE resume.

Acceptance coverage (Controller mailbox #74 / M3):
  1. Same ordered events always produce identical state  -> golden + repeat tests
  2. Replay sequence rewinds all visible surfaces consistently -> surface sync tests
  3. Duplicate/stale/gap behavior matches M0/M2 contracts -> anomaly parity tests
  4. Golden replay fixtures + representative rewind sequences -> golden/path tests
  5. LIVE state can resume after replay without sequence corruption -> resume tests
"""

import unittest

from dw_observation.events import RunProjectionEvent
from dw_observation.reducer import reduce as reduce_events
from dw_observation.replay import (
    MODE_LIVE,
    MODE_REPLAY,
    ReplayFrame,
    ReplaySession,
    ReplayTimeline,
    project_surfaces,
)


def ev(
    seq,
    event_type,
    *,
    source="taskcontroller",
    eid=None,
    run="RUN-M3",
    when=None,
    gate=None,
    node=None,
    outcome=None,
    evidence=None,
    authority=None,
    actor="ChatGPT TaskController",
):
    """Build a canonical RunProjectionEvent with deterministic identity."""
    return RunProjectionEvent(
        occurred_at=when or f"2026-08-23T10:{seq:02d}:00Z",
        run_id=run,
        source_event_id=eid or f"{source}_evt_{seq}",
        source_system=source,
        source_digest=f"sha256:digest_{source}_{seq}",
        sequence=seq,
        event_type=event_type,
        gate=gate,
        node_id=node,
        outcome=outcome,
        actor=actor,
        evidence_refs=list(evidence or []),
        authority_ref=authority,
    )


def canonical_stream():
    """A representative run: start -> gates -> node progress -> completion."""
    return [
        ev(0, "run_started"),
        ev(1, "gate_approved", gate="G2", authority="G2-DW-OBS-R1"),
        ev(2, "node_started", node="M3", outcome="active"),
        ev(3, "node_progress", node="M3", outcome="active", evidence=["pr://74"]),
        ev(4, "gate_passed", gate="G3", authority="G3-DW-OBS-R1", evidence=["ci://run/1"]),
        ev(5, "node_completed", node="M3", outcome="done"),
        ev(6, "run_completed"),
    ]


class TestReplayDeterminism(unittest.TestCase):
    """Acceptance 1: same ordered events always produce identical state."""

    def test_frame_equals_reduce_of_prefix(self):
        events = canonical_stream()
        tl = ReplayTimeline(events)
        for cursor in tl.cursors():
            frame = tl.frame_at(cursor)
            expected = reduce_events(events[:cursor])
            self.assertEqual(frame.projection.to_dict(), expected.to_dict())
            self.assertEqual(frame.cursor, cursor)

    def test_repeated_replay_is_byte_identical(self):
        tl = ReplayTimeline(canonical_stream())
        first = [f.state_digest for f in tl.frames()]
        for _ in range(5):
            self.assertEqual([f.state_digest for f in tl.frames()], first)

    def test_verify_determinism_helper(self):
        self.assertTrue(ReplayTimeline(canonical_stream()).verify_determinism(repeats=4))

    def test_replay_digest_stable_across_instances(self):
        a = ReplayTimeline(canonical_stream()).replay_digest()
        b = ReplayTimeline(canonical_stream()).replay_digest()
        self.assertEqual(a, b)

    def test_replay_digest_changes_when_order_changes(self):
        events = canonical_stream()
        swapped = list(events)
        swapped[1], swapped[2] = swapped[2], swapped[1]
        self.assertNotEqual(
            ReplayTimeline(events).replay_digest(),
            ReplayTimeline(swapped).replay_digest(),
        )

    def test_replay_digest_covers_intermediate_states_not_just_tip(self):
        """Two streams with the same tip but different paths must differ."""
        base = canonical_stream()
        # Re-emit the same node event earlier: tip state identical, path differs.
        extra = [base[0], base[2], base[1]] + base[2:]
        self.assertNotEqual(
            ReplayTimeline(base).replay_digest(),
            ReplayTimeline(extra).replay_digest(),
        )

    def test_empty_stream_replays_to_empty_frame(self):
        tl = ReplayTimeline([])
        self.assertEqual(tl.total, 0)
        frame = tl.tip()
        self.assertTrue(frame.at_tip)
        self.assertTrue(frame.at_start)
        self.assertIsNone(frame.last_event)
        self.assertEqual(frame.projection.events, [])

    def test_timeline_does_not_mutate_or_reorder_source(self):
        events = canonical_stream()
        snapshot = list(events)
        tl = ReplayTimeline(events)
        tl.frames()
        self.assertEqual(events, snapshot)
        self.assertEqual(list(tl.events), snapshot)


class TestGoldenReplayFixture(unittest.TestCase):
    """Acceptance 4: golden replay fixtures pin exact per-cursor state."""

    def test_golden_cursor_progression(self):
        tl = ReplayTimeline(canonical_stream())

        # cursor 0 — nothing observed yet.
        f0 = tl.frame_at(0)
        self.assertEqual(f0.projection.run_id, None)
        self.assertEqual(f0.projection.nodes, {})
        self.assertEqual(f0.projection.gates, {})

        # cursor 2 — run started + G2 approved, node not yet started.
        f2 = tl.frame_at(2)
        self.assertEqual(f2.projection.run_id, "RUN-M3")
        self.assertEqual(f2.projection.gates["G2"].status, "approved")
        self.assertNotIn("M3", f2.projection.nodes)

        # cursor 4 — node active, G3 not yet passed.
        f4 = tl.frame_at(4)
        self.assertEqual(f4.projection.nodes["M3"].status, "active")
        self.assertNotIn("G3", f4.projection.gates)

        # cursor 5 — G3 passed.
        f5 = tl.frame_at(5)
        self.assertEqual(f5.projection.gates["G3"].status, "passed")

        # tip — node done, both gates terminal.
        tip = tl.tip()
        self.assertEqual(tip.projection.nodes["M3"].status, "done")
        self.assertEqual(tip.projection.gates["G2"].status, "approved")
        self.assertEqual(tip.projection.gates["G3"].status, "passed")
        self.assertTrue(tip.at_tip)

    def test_golden_state_digests_are_distinct_per_cursor(self):
        tl = ReplayTimeline(canonical_stream())
        digests = [f.state_digest for f in tl.frames()]
        self.assertEqual(len(digests), len(set(digests)))

    def test_frame_reports_applied_counts_and_head(self):
        tl = ReplayTimeline(canonical_stream())
        f3 = tl.frame_at(3)
        self.assertEqual(f3.events_applied, 3)
        self.assertEqual(len(f3.projection.events), 3)
        head = f3.last_event
        self.assertIsNotNone(head)
        assert head is not None
        self.assertEqual(head.source_event_id, "taskcontroller_evt_2")

    def test_cursor_clamped_into_range(self):
        tl = ReplayTimeline(canonical_stream())
        self.assertEqual(tl.frame_at(-10).cursor, 0)
        self.assertEqual(tl.frame_at(999).cursor, tl.total)


class TestAnomalyParityWithM0M2(unittest.TestCase):
    """Acceptance 3: duplicate / out-of-order / stale / gap match M0/M2."""

    def test_duplicate_surfaces_in_replay(self):
        dup = ev(1, "node_progress", node="M3")
        events = [ev(0, "run_started"), dup, dup]
        tip = ReplayTimeline(events).tip()
        kinds = [a.kind for a in tip.anomalies]
        self.assertIn("DUPLICATE", kinds)
        # Parity with the M0 reducer, exactly.
        self.assertEqual(
            [a.kind for a in reduce_events(events).anomalies], kinds
        )

    def test_gap_surfaces_in_replay(self):
        events = [ev(0, "run_started"), ev(1, "node_progress", node="M3"), ev(4, "node_progress", node="M3")]
        tip = ReplayTimeline(events).tip()
        self.assertIn("GAP", [a.kind for a in tip.anomalies])
        self.assertEqual(
            [a.kind for a in reduce_events(events).anomalies],
            [a.kind for a in tip.anomalies],
        )

    def test_out_of_order_surfaces_in_replay(self):
        events = [ev(0, "run_started"), ev(3, "node_progress", node="M3"), ev(2, "node_progress", node="M3")]
        tip = ReplayTimeline(events).tip()
        self.assertIn("OUT_OF_ORDER", [a.kind for a in tip.anomalies])

    def test_stale_surfaces_in_replay(self):
        events = [
            ev(0, "run_started", when="2026-08-23T10:00:00Z"),
            ev(5, "node_progress", node="M3", when="2026-08-23T12:00:00Z"),
            ev(4, "node_progress", node="M3", when="2026-08-23T11:00:00Z", eid="late"),
        ]
        tip = ReplayTimeline(events).tip()
        kinds = [a.kind for a in tip.anomalies]
        self.assertTrue({"STALE", "OUT_OF_ORDER"} & set(kinds))
        self.assertEqual([a.kind for a in reduce_events(events).anomalies], kinds)

    def test_anomaly_visible_only_from_its_own_cursor_onward(self):
        dup = ev(1, "node_progress", node="M3")
        events = [ev(0, "run_started"), dup, dup, ev(2, "run_completed")]
        tl = ReplayTimeline(events)
        # Before the duplicate is applied, no anomaly exists yet.
        self.assertEqual(len(tl.frame_at(2).anomalies), 0)
        # Once applied, it is surfaced and never hidden again.
        self.assertGreaterEqual(len(tl.frame_at(3).anomalies), 1)
        self.assertGreaterEqual(len(tl.tip().anomalies), 1)

    def test_anomalies_never_dropped_by_rewinding_forward_again(self):
        dup = ev(1, "node_progress", node="M3")
        tl = ReplayTimeline([ev(0, "run_started"), dup, dup])
        before = len(tl.tip().anomalies)
        tl.rewind_sequence([3, 0, 2, 3])
        self.assertEqual(len(tl.tip().anomalies), before)

    def test_anomaly_kind_counts_reported(self):
        dup = ev(1, "node_progress", node="M3")
        tl = ReplayTimeline([ev(0, "run_started"), dup, dup])
        counts = tl.tip().anomaly_kinds()
        self.assertEqual(counts["DUPLICATE"], 1)
        self.assertEqual(counts["GAP"], 0)

    def test_cross_source_interleaving_raises_no_false_anomaly(self):
        """Parity with M0: TC and GWC sequences are independent ledgers."""
        events = [
            ev(0, "run_started", source="taskcontroller"),
            ev(0, "gate_passed", source="gwc", gate="G3"),
            ev(1, "node_progress", source="taskcontroller", node="M3"),
            ev(1, "gate_released", source="gwc", gate="G3"),
        ]
        self.assertEqual(ReplayTimeline(events).tip().anomalies, ())


class TestSurfaceSynchronization(unittest.TestCase):
    """Acceptance 2: a rewind moves ALL visible surfaces together."""

    def test_all_surfaces_share_cursor_and_digest(self):
        tl = ReplayTimeline(canonical_stream())
        for cursor in tl.cursors():
            snap = project_surfaces(tl.frame_at(cursor))
            self.assertTrue(snap.synchronized(), f"desync at cursor {cursor}")

    def test_five_surfaces_present(self):
        snap = project_surfaces(ReplayTimeline(canonical_stream()).tip())
        self.assertEqual(
            set(snap.surfaces),
            {"root_card", "dag", "timeline", "evidence", "inspector"},
        )

    def test_rewind_hides_later_evidence(self):
        tl = ReplayTimeline(canonical_stream())
        tip_refs = project_surfaces(tl.tip()).evidence["refs"]
        early_refs = project_surfaces(tl.frame_at(2)).evidence["refs"]
        self.assertGreater(len(tip_refs), len(early_refs))
        self.assertEqual(early_refs, [])

    def test_rewind_hides_later_gates_from_dag(self):
        tl = ReplayTimeline(canonical_stream())
        self.assertNotIn("G3", project_surfaces(tl.frame_at(2)).dag["gates"])
        self.assertIn("G3", project_surfaces(tl.tip()).dag["gates"])

    def test_timeline_surface_reports_pending_count(self):
        tl = ReplayTimeline(canonical_stream())
        snap = project_surfaces(tl.frame_at(3))
        self.assertEqual(snap.timeline["pending_count"], tl.total - 3)
        self.assertEqual(len(snap.timeline["applied"]), 3)

    def test_inspector_shows_head_event_before_after(self):
        tl = ReplayTimeline(canonical_stream())
        selected = project_surfaces(tl.frame_at(1)).inspector["selected"]
        self.assertEqual(selected["source_event_id"], "taskcontroller_evt_0")

    def test_root_card_marks_unknown_when_absent(self):
        snap = project_surfaces(ReplayTimeline([]).tip())
        self.assertEqual(snap.root_card["run_id"], "—")
        self.assertEqual(snap.root_card["started_at"], "—")

    def test_representative_rewind_sequence_stays_consistent(self):
        tl = ReplayTimeline(canonical_stream())
        path = [7, 0, 3, 1, 6, 3, 7, 2, 7]
        self.assertTrue(tl.is_path_consistent(path))
        frames = tl.rewind_sequence(path)
        self.assertEqual([f.cursor for f in frames], path)
        for f in frames:
            self.assertTrue(project_surfaces(f).synchronized())

    def test_revisiting_a_cursor_yields_identical_state(self):
        tl = ReplayTimeline(canonical_stream())
        a = tl.frame_at(3).state_digest
        tl.rewind_sequence([0, 7, 1])
        self.assertEqual(tl.frame_at(3).state_digest, a)

    def test_surface_snapshot_serializes(self):
        snap = project_surfaces(ReplayTimeline(canonical_stream()).tip())
        d = snap.to_dict()
        self.assertEqual(d["cursor"], snap.cursor)
        self.assertIn("surfaces", d)


class TestLiveResume(unittest.TestCase):
    """Acceptance 5: LIVE resumes after replay without sequence corruption."""

    def test_session_starts_live_at_tip(self):
        s = ReplaySession(canonical_stream())
        self.assertEqual(s.mode, MODE_LIVE)
        self.assertEqual(s.cursor, s.total)
        self.assertTrue(s.frame().at_tip)

    def test_enter_replay_and_resume_returns_to_identical_tip(self):
        events = canonical_stream()
        s = ReplaySession(events)
        tip_before = s.frame().state_digest
        s.enter_replay(2)
        self.assertEqual(s.mode, MODE_REPLAY)
        self.assertEqual(s.cursor, 2)
        resumed = s.resume_live()
        self.assertEqual(s.mode, MODE_LIVE)
        self.assertEqual(resumed.state_digest, tip_before)

    def test_events_arriving_while_rewound_are_not_lost(self):
        s = ReplaySession(canonical_stream())
        s.enter_replay(1)
        self.assertEqual(s.cursor, 1)
        s.append_live(ev(7, "readback_completed"))
        # Cursor deliberately stays in the past ...
        self.assertEqual(s.cursor, 1)
        # ... but the event is retained and visible on resume.
        self.assertEqual(s.total, 8)
        self.assertEqual(s.resume_live().cursor, 8)

    def test_resume_matches_never_replayed_session(self):
        events = canonical_stream()
        late = ev(7, "readback_completed")

        replayed = ReplaySession(events)
        replayed.enter_replay(0)
        replayed.append_live(late)
        replayed.rewind_to(3)
        replayed.step_forward(2)
        resumed = replayed.resume_live()

        never = ReplaySession(events)
        never.append_live(late)

        self.assertEqual(resumed.state_digest, never.frame().state_digest)
        self.assertEqual(
            resumed.projection.to_dict(), never.frame().projection.to_dict()
        )

    def test_high_water_state_uncorrupted_after_replay(self):
        """Sequence/high-water state must equal a straight reduce of the stream."""
        events = canonical_stream()
        s = ReplaySession(events)
        s.enter_replay(0)
        for c in (2, 5, 1, 7, 3):
            s.rewind_to(c)
        resumed = s.resume_live()
        self.assertEqual(
            resumed.projection.to_dict(), reduce_events(events).to_dict()
        )
        self.assertEqual(resumed.anomalies, ())

    def test_live_mode_cursor_follows_tip(self):
        s = ReplaySession(canonical_stream())
        n = s.total
        s.append_live(ev(7, "readback_completed"))
        self.assertEqual(s.cursor, n + 1)
        self.assertTrue(s.frame().at_tip)

    def test_step_back_and_forward_clamp(self):
        s = ReplaySession(canonical_stream())
        s.enter_replay()
        s.step_back(100)
        self.assertEqual(s.cursor, 0)
        s.step_forward(100)
        self.assertEqual(s.cursor, s.total)

    def test_rewind_path_returns_synchronized_snapshots(self):
        s = ReplaySession(canonical_stream())
        snaps = s.rewind_path([0, 3, 7, 2])
        self.assertEqual([x.cursor for x in snaps], [0, 3, 7, 2])
        for x in snaps:
            self.assertTrue(x.synchronized())
            self.assertEqual(x.mode, MODE_REPLAY)

    def test_surfaces_tagged_live_after_resume(self):
        s = ReplaySession(canonical_stream())
        s.enter_replay(1)
        self.assertEqual(s.surfaces().mode, MODE_REPLAY)
        s.resume_live()
        self.assertEqual(s.surfaces().mode, MODE_LIVE)

    def test_replay_never_mutates_underlying_stream_order(self):
        events = canonical_stream()
        ids_before = [e.source_event_id for e in events]
        s = ReplaySession(events)
        s.enter_replay(0)
        s.rewind_to(4)
        s.resume_live()
        self.assertEqual(
            [e.source_event_id for e in s.timeline().events], ids_before
        )

    def test_extend_live_appends_in_order(self):
        s = ReplaySession(canonical_stream())
        s.extend_live([ev(7, "readback_completed"), ev(8, "run_completed", eid="tail")])
        tail = [e.source_event_id for e in s.timeline().events][-2:]
        self.assertEqual(tail, ["taskcontroller_evt_7", "tail"])

    def test_replay_on_empty_session_is_safe(self):
        s = ReplaySession()
        f = s.enter_replay()
        self.assertTrue(f.at_start and f.at_tip)
        self.assertEqual(s.resume_live().cursor, 0)


if __name__ == "__main__":
    unittest.main()
