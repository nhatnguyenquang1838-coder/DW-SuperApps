import { describe, expect, it } from "vitest";
import type { ProjectionEvent } from "@/lib/live";
import {
  ReplaySession,
  ReplayTimeline,
  UNKNOWN,
  anomalyKindCounts,
  digestOf,
  isSynchronized,
  projectSurfaces,
  reduceEvents,
  stableStringify,
  surfacesOf,
} from "@/lib/replay";

// M3 — deterministic replay + synchronized whole-screen rewind (browser peer).
//
// Acceptance coverage:
//   1. same ordered events -> identical state (determinism / digest tests)
//   2. rewind moves ALL surfaces consistently (surface sync tests)
//   3. duplicate/stale/gap parity with M0/M2 (anomaly tests)
//   4. golden replay fixture + representative rewind sequences
//   5. LIVE resumes after replay without sequence corruption (session tests)

function ev(
  seq: number,
  eventType: string,
  extra: Partial<ProjectionEvent> & Record<string, unknown> = {}
): ProjectionEvent {
  const source = (extra.source_system as string) ?? "taskcontroller";
  return {
    run_id: "RUN-M3",
    source_system: source,
    source_event_id: (extra.source_event_id as string) ?? `${source}_evt_${seq}`,
    sequence: seq,
    projection_ordinal: (extra.projection_ordinal as number) ?? seq + 1,
    occurred_at: (extra.occurred_at as string) ?? `2026-08-23T10:${String(seq).padStart(2, "0")}:00Z`,
    event_type: eventType,
    ...extra,
  } as ProjectionEvent;
}

function stream(): ProjectionEvent[] {
  return [
    ev(0, "run_started", { actor: "ChatGPT TaskController" }),
    ev(1, "gate_approved", { gate: "G2", authority_ref: "G2-DW-OBS-R1", actor: "Human" }),
    ev(2, "node_started", { node_id: "M3", outcome: "active", actor: "Hermes Mac" }),
    ev(3, "node_progress", {
      node_id: "M3",
      outcome: "active",
      evidence_refs: ["pr://74"],
      actor: "Hermes Mac",
    }),
    ev(4, "gate_passed", {
      gate: "G3",
      authority_ref: "G3-DW-OBS-R1",
      evidence_refs: ["ci://run/1"],
      actor: "ChatGPT TaskController",
    }),
    ev(5, "node_completed", { node_id: "M3", outcome: "done", actor: "Hermes Mac" }),
    ev(6, "run_completed", { actor: "ChatGPT TaskController" }),
  ];
}

describe("stable digest", () => {
  it("is key-order independent", () => {
    expect(stableStringify({ a: 1, b: 2 })).toBe(stableStringify({ b: 2, a: 1 }));
    expect(digestOf({ a: 1, b: 2 })).toBe(digestOf({ b: 2, a: 1 }));
  });

  it("differs for different values", () => {
    expect(digestOf({ a: 1 })).not.toBe(digestOf({ a: 2 }));
  });

  it("handles nested arrays and nulls deterministically", () => {
    const v = { xs: [1, null, { y: "z" }] };
    expect(digestOf(v)).toBe(digestOf(JSON.parse(JSON.stringify(v))));
  });
});

describe("prefix reducer determinism (acceptance 1)", () => {
  it("frameAt(N) equals reduce of the first N events", () => {
    const events = stream();
    const tl = new ReplayTimeline(events);
    for (const c of tl.cursors()) {
      const frame = tl.frameAt(c);
      const expected = reduceEvents(events.slice(0, c));
      expect(frame.projection.nodes).toEqual(expected.nodes);
      expect(frame.projection.gates).toEqual(expected.gates);
      expect(frame.projection.events.length).toBe(c);
    }
  });

  it("repeated replays are identical", () => {
    const tl = new ReplayTimeline(stream());
    const first = tl.frames().map((f) => f.stateDigest);
    for (let i = 0; i < 5; i++) {
      expect(tl.frames().map((f) => f.stateDigest)).toEqual(first);
    }
    expect(tl.verifyDeterminism(4)).toBe(true);
  });

  it("replayDigest is stable across instances", () => {
    expect(new ReplayTimeline(stream()).replayDigest()).toBe(
      new ReplayTimeline(stream()).replayDigest()
    );
  });

  it("replayDigest changes when order changes", () => {
    const a = stream();
    const b = stream();
    [b[1], b[2]] = [b[2], b[1]];
    expect(new ReplayTimeline(a).replayDigest()).not.toBe(
      new ReplayTimeline(b).replayDigest()
    );
  });

  it("does not mutate the caller's array", () => {
    const events = stream();
    const ids = events.map((e) => e.source_event_id);
    const tl = new ReplayTimeline(events);
    tl.frames();
    expect(events.map((e) => e.source_event_id)).toEqual(ids);
  });

  it("clamps out-of-range cursors", () => {
    const tl = new ReplayTimeline(stream());
    expect(tl.frameAt(-5).cursor).toBe(0);
    expect(tl.frameAt(999).cursor).toBe(tl.total);
    expect(tl.frameAt(Number.NaN).cursor).toBe(0);
  });

  it("empty stream replays safely", () => {
    const tl = new ReplayTimeline([]);
    expect(tl.total).toBe(0);
    const f = tl.tip();
    expect(f.atTip && f.atStart).toBe(true);
    expect(f.projection.runId).toBeNull();
  });
});

describe("golden replay fixture (acceptance 4)", () => {
  it("pins state at each milestone cursor", () => {
    const tl = new ReplayTimeline(stream());

    expect(tl.frameAt(0).projection.runId).toBeNull();
    expect(tl.frameAt(0).projection.gates).toEqual({});

    expect(tl.frameAt(2).projection.gates.G2.status).toBe("approved");
    expect(tl.frameAt(2).projection.nodes.M3).toBeUndefined();

    expect(tl.frameAt(4).projection.nodes.M3.status).toBe("active");
    expect(tl.frameAt(4).projection.gates.G3).toBeUndefined();

    expect(tl.frameAt(5).projection.gates.G3.status).toBe("passed");

    const tip = tl.tip();
    expect(tip.projection.nodes.M3.status).toBe("done");
    expect(tip.atTip).toBe(true);
  });

  it("gives every cursor a distinct digest", () => {
    const digests = new ReplayTimeline(stream()).frames().map((f) => f.stateDigest);
    expect(new Set(digests).size).toBe(digests.length);
  });

  it("preserves gate_failed as failed, never released", () => {
    const events = [ev(0, "run_started"), ev(1, "gate_failed", { gate: "G3", actor: "ci" })];
    const proj = reduceEvents(events);
    expect(proj.gates.G3.status).toBe("failed");
    expect(proj.gates.G3.failedBy).toBe("ci");
    expect(proj.gates.G3.releasedBy).toBe(UNKNOWN);
  });
});

describe("anomaly parity with M0/M2 (acceptance 3)", () => {
  it("detects DUPLICATE", () => {
    const dup = ev(1, "node_progress", { node_id: "M3" });
    const kinds = reduceEvents([ev(0, "run_started"), dup, dup]).anomalies.map((a) => a.kind);
    expect(kinds).toContain("DUPLICATE");
  });

  it("detects GAP on a forward jump", () => {
    const kinds = reduceEvents([
      ev(0, "run_started"),
      ev(1, "node_progress", { node_id: "M3" }),
      ev(4, "node_progress", { node_id: "M3" }),
    ]).anomalies.map((a) => a.kind);
    expect(kinds).toContain("GAP");
  });

  it("detects OUT_OF_ORDER on a regression", () => {
    const kinds = reduceEvents([
      ev(0, "run_started"),
      ev(3, "node_progress", { node_id: "M3" }),
      ev(2, "node_progress", { node_id: "M3" }),
    ]).anomalies.map((a) => a.kind);
    expect(kinds).toContain("OUT_OF_ORDER");
  });

  it("detects STALE when a later-arriving event is behind the high-water", () => {
    const kinds = reduceEvents([
      ev(0, "run_started", { occurred_at: "2026-08-23T10:00:00Z" }),
      ev(5, "node_progress", { node_id: "M3", occurred_at: "2026-08-23T12:00:00Z" }),
      ev(4, "node_progress", {
        node_id: "M3",
        occurred_at: "2026-08-23T11:00:00Z",
        source_event_id: "late",
      }),
    ]).anomalies.map((a) => a.kind);
    expect(kinds.some((k) => k === "STALE" || k === "OUT_OF_ORDER")).toBe(true);
  });

  it("does not raise false anomalies across independent source ledgers", () => {
    const proj = reduceEvents([
      ev(0, "run_started", { source_system: "taskcontroller" }),
      ev(0, "gate_passed", { source_system: "gwc", gate: "G3" }),
      ev(1, "node_progress", { source_system: "taskcontroller", node_id: "M3" }),
      ev(1, "gate_released", { source_system: "gwc", gate: "G3" }),
    ]);
    expect(proj.anomalies).toEqual([]);
  });

  it("never fabricates a sequence for an event without one", () => {
    const noSeq = { ...ev(1, "node_progress", { node_id: "M3" }) };
    delete (noSeq as Record<string, unknown>).sequence;
    const proj = reduceEvents([ev(0, "run_started"), noSeq as ProjectionEvent]);
    expect(proj.anomalies).toEqual([]);
    expect(proj.events.length).toBe(2);
  });

  it("surfaces an anomaly only from its own cursor onward", () => {
    const dup = ev(1, "node_progress", { node_id: "M3" });
    const tl = new ReplayTimeline([ev(0, "run_started"), dup, dup, ev(2, "run_completed")]);
    expect(tl.frameAt(2).anomalies.length).toBe(0);
    expect(tl.frameAt(3).anomalies.length).toBeGreaterThan(0);
  });

  it("counts anomaly kinds explicitly", () => {
    const dup = ev(1, "node_progress", { node_id: "M3" });
    const counts = anomalyKindCounts(
      new ReplayTimeline([ev(0, "run_started"), dup, dup]).tip().anomalies
    );
    expect(counts.DUPLICATE).toBe(1);
    expect(counts.GAP).toBe(0);
  });
});

describe("whole-screen surface synchronization (acceptance 2)", () => {
  it("all five surfaces share cursor and digest at every position", () => {
    const tl = new ReplayTimeline(stream());
    for (const c of tl.cursors()) {
      const snap = projectSurfaces(tl.frameAt(c));
      expect(isSynchronized(snap)).toBe(true);
      expect(Object.keys(surfacesOf(snap)).sort()).toEqual([
        "dag",
        "evidence",
        "inspector",
        "rootCard",
        "timeline",
      ]);
    }
  });

  it("rewinding hides evidence that had not happened yet", () => {
    const tl = new ReplayTimeline(stream());
    expect((projectSurfaces(tl.frameAt(2)).evidence.refs as unknown[]).length).toBe(0);
    expect(
      (projectSurfaces(tl.tip()).evidence.refs as unknown[]).length
    ).toBeGreaterThan(0);
  });

  it("rewinding hides later gates from the DAG", () => {
    const tl = new ReplayTimeline(stream());
    expect(projectSurfaces(tl.frameAt(2)).dag.gates).not.toHaveProperty("G3");
    expect(projectSurfaces(tl.tip()).dag.gates).toHaveProperty("G3");
  });

  it("reports pending count on the timeline surface", () => {
    const tl = new ReplayTimeline(stream());
    const snap = projectSurfaces(tl.frameAt(3));
    expect(snap.timeline.pendingCount).toBe(tl.total - 3);
    expect((snap.timeline.applied as unknown[]).length).toBe(3);
  });

  it("marks unknown values explicitly instead of inventing them", () => {
    const snap = projectSurfaces(new ReplayTimeline([]).tip());
    expect(snap.rootCard.runId).toBe(UNKNOWN);
    expect(snap.rootCard.startedAt).toBe(UNKNOWN);
    expect(snap.inspector.selected).toBeNull();
  });

  it("stays consistent across a representative rewind sequence", () => {
    const tl = new ReplayTimeline(stream());
    const path = [7, 0, 3, 1, 6, 3, 7, 2, 7];
    expect(tl.isPathConsistent(path)).toBe(true);
    for (const f of tl.rewindSequence(path)) {
      expect(isSynchronized(projectSurfaces(f))).toBe(true);
    }
  });

  it("returns identical state when a cursor is revisited", () => {
    const tl = new ReplayTimeline(stream());
    const before = tl.frameAt(3).stateDigest;
    tl.rewindSequence([0, 7, 1]);
    expect(tl.frameAt(3).stateDigest).toBe(before);
  });
});

describe("LIVE resume without sequence corruption (acceptance 5)", () => {
  it("starts LIVE at the tip", () => {
    const s = new ReplaySession(stream());
    expect(s.mode).toBe("LIVE");
    expect(s.cursor).toBe(s.total);
    expect(s.frame().atTip).toBe(true);
  });

  it("resumes to the identical tip digest after replay", () => {
    const s = new ReplaySession(stream());
    const tipBefore = s.frame().stateDigest;
    s.enterReplay(2);
    expect(s.mode).toBe("REPLAY");
    expect(s.cursor).toBe(2);
    expect(s.resumeLive().stateDigest).toBe(tipBefore);
    expect(s.mode).toBe("LIVE");
  });

  it("retains live events that arrive while rewound", () => {
    const s = new ReplaySession(stream());
    s.enterReplay(1);
    s.appendLive(ev(7, "readback_completed"));
    expect(s.cursor).toBe(1); // operator stays in the past
    expect(s.total).toBe(8); // nothing lost
    expect(s.resumeLive().cursor).toBe(8);
  });

  it("resumed state equals a never-replayed session", () => {
    const events = stream();
    const late = ev(7, "readback_completed");

    const replayed = new ReplaySession(events);
    replayed.enterReplay(0);
    replayed.appendLive(late);
    replayed.rewindTo(3);
    replayed.stepForward(2);
    const resumed = replayed.resumeLive();

    const never = new ReplaySession(events);
    never.appendLive(late);

    expect(resumed.stateDigest).toBe(never.frame().stateDigest);
    expect(resumed.projection.nodes).toEqual(never.frame().projection.nodes);
    expect(resumed.projection.gates).toEqual(never.frame().projection.gates);
  });

  it("keeps high-water/sequence state intact after a rewind path", () => {
    const events = stream();
    const s = new ReplaySession(events);
    s.enterReplay(0);
    for (const c of [2, 5, 1, 7, 3]) s.rewindTo(c);
    const resumed = s.resumeLive();
    const direct = reduceEvents(events);
    expect(resumed.projection.nodes).toEqual(direct.nodes);
    expect(resumed.projection.gates).toEqual(direct.gates);
    expect(resumed.anomalies).toEqual([]);
  });

  it("clamps step back/forward at the boundaries", () => {
    const s = new ReplaySession(stream());
    s.enterReplay();
    s.stepBack(100);
    expect(s.cursor).toBe(0);
    s.stepForward(100);
    expect(s.cursor).toBe(s.total);
  });

  it("tags snapshots with the current mode", () => {
    const s = new ReplaySession(stream());
    s.enterReplay(1);
    expect(s.surfaces().mode).toBe("REPLAY");
    s.resumeLive();
    expect(s.surfaces().mode).toBe("LIVE");
  });

  it("walks a rewind path returning synchronized snapshots", () => {
    const s = new ReplaySession(stream());
    const snaps = s.rewindPath([0, 3, 7, 2]);
    expect(snaps.map((x) => x.cursor)).toEqual([0, 3, 7, 2]);
    for (const x of snaps) expect(isSynchronized(x)).toBe(true);
  });

  it("never reorders the underlying stream", () => {
    const events = stream();
    const ids = events.map((e) => e.source_event_id);
    const s = new ReplaySession(events);
    s.enterReplay(0);
    s.rewindTo(4);
    s.resumeLive();
    expect(s.timeline().events.map((e) => e.source_event_id)).toEqual(ids);
  });

  it("replays safely on an empty session", () => {
    const s = new ReplaySession();
    const f = s.enterReplay();
    expect(f.atStart && f.atTip).toBe(true);
    expect(s.resumeLive().cursor).toBe(0);
  });
});
