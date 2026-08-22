import { describe, expect, it } from "vitest";
import type { ProjectionEvent } from "@/lib/live";
import {
  REDUCER_VERSION,
  compareRuns,
  handoffProfile,
  longestWait,
  recoveryProfile,
  retryProfile,
  reviewRun,
  runDuration,
  traceOf,
} from "@/lib/reviewIntelligence";

// M4 — review intelligence from immutable projection history.
//
// Acceptance coverage (Controller mailbox #74 / M4):
//   1. Metrics reproducible from projection events
//   2. Aggregates trace back to exact event/evidence refs
//   3. Unknown/incomplete history visibly marked
//   4. Compare-runs warns for incompatible reducer/schema versions
//   5. Tests cover duration, retry, recovery and handoff derivation

function ev(
  seq: number,
  eventType: string,
  extra: Record<string, unknown> = {}
): ProjectionEvent {
  const source = (extra.source_system as string) ?? "taskcontroller";
  return {
    run_id: "RUN-M4",
    source_system: source,
    source_event_id: (extra.source_event_id as string) ?? `${source}_evt_${seq}`,
    sequence: seq,
    projection_ordinal: seq + 1,
    occurred_at: (extra.occurred_at as string) ?? `2026-08-23T10:${String(seq).padStart(2, "0")}:00Z`,
    event_type: eventType,
    ...extra,
  } as ProjectionEvent;
}

/** A run with a failure, a recovery, a retry and two actor handoffs. */
function richStream(): ProjectionEvent[] {
  return [
    ev(0, "run_started", { actor: "ChatGPT TaskController", occurred_at: "2026-08-23T10:00:00Z" }),
    ev(1, "gate_approved", {
      gate: "G2",
      actor: "Human",
      authority_ref: "G2-R1",
      occurred_at: "2026-08-23T10:01:00Z",
    }),
    ev(2, "node_started", {
      node_id: "M4",
      outcome: "active",
      actor: "Hermes Mac",
      occurred_at: "2026-08-23T10:02:00Z",
    }),
    ev(3, "gate_failed", {
      gate: "G3",
      actor: "ci",
      evidence_refs: ["ci://run/1"],
      occurred_at: "2026-08-23T10:05:00Z",
    }),
    ev(4, "gate_passed", {
      gate: "G3",
      actor: "ci",
      evidence_refs: ["ci://run/2"],
      occurred_at: "2026-08-23T10:12:00Z",
    }),
    ev(5, "node_completed", {
      node_id: "M4",
      outcome: "done",
      actor: "Hermes Mac",
      occurred_at: "2026-08-23T10:15:00Z",
    }),
    ev(6, "run_completed", {
      actor: "ChatGPT TaskController",
      occurred_at: "2026-08-23T10:16:00Z",
    }),
  ];
}

describe("duration derivation (acceptance 5)", () => {
  it("computes the exact wall-clock span from recorded timestamps", () => {
    const m = runDuration(richStream());
    expect(m.value?.totalMs).toBe(16 * 60 * 1000);
    expect(m.value?.terminated).toBe(true);
    expect(m.confidence).toBe("EXACT");
    expect(m.incomplete).toEqual([]);
  });

  it("marks an unterminated run instead of implying completion", () => {
    const events = richStream().slice(0, 3);
    const m = runDuration(events);
    expect(m.value?.terminated).toBe(false);
    expect(m.incomplete).toContain("UNTERMINATED");
    expect(m.confidence).toBe("PARTIAL");
  });

  it("returns null (not zero) with no events", () => {
    const m = runDuration([]);
    expect(m.value).toBeNull();
    expect(m.confidence).toBe("UNKNOWN");
    expect(m.incomplete).toContain("NO_EVENTS");
  });

  it("marks MISSING_TIMESTAMP when a timestamp is absent", () => {
    const bad = ev(1, "node_progress", { node_id: "M4" });
    delete (bad as Record<string, unknown>).occurred_at;
    const m = runDuration([ev(0, "run_started"), bad, ev(2, "run_completed")]);
    expect(m.incomplete).toContain("MISSING_TIMESTAMP");
    expect(m.confidence).toBe("PARTIAL");
  });

  it("is reproducible across repeated derivations", () => {
    const a = runDuration(richStream());
    const b = runDuration(richStream());
    expect(a.value).toEqual(b.value);
    expect(a.trace).toEqual(b.trace);
  });
});

describe("wait derivation", () => {
  it("finds the longest quiet interval", () => {
    const m = longestWait(richStream());
    expect(m.value?.ms).toBe(7 * 60 * 1000);
    expect(m.value?.fromEventId).toBe("taskcontroller_evt_3");
    expect(m.value?.toEventId).toBe("taskcontroller_evt_4");
  });

  it("returns null with fewer than two timed events", () => {
    const m = longestWait([ev(0, "run_started")]);
    expect(m.value).toBeNull();
    expect(m.confidence).toBe("UNKNOWN");
  });
});

describe("retry derivation (acceptance 5)", () => {
  it("counts repeated attempts per gate/node", () => {
    const m = retryProfile(richStream());
    const g3 = m.value?.find((s) => s.key === "gate:G3");
    expect(g3?.attempts).toBe(2);
    expect(g3?.eventIds).toEqual(["taskcontroller_evt_3", "taskcontroller_evt_4"]);
  });

  it("omits single-attempt targets", () => {
    const m = retryProfile(richStream());
    expect(m.value?.some((s) => s.key === "gate:G2")).toBe(false);
  });

  it("returns null when no gate/node events exist", () => {
    const m = retryProfile([ev(0, "run_started")]);
    expect(m.value).toBeNull();
    expect(m.incomplete).toContain("NO_MATCHING_EVENTS");
  });
});

describe("recovery derivation (acceptance 5)", () => {
  it("pairs a failure with its recovery and measures the span", () => {
    const m = recoveryProfile(richStream());
    expect(m.value?.length).toBe(1);
    const span = m.value![0];
    expect(span.target).toBe("gate:G3");
    expect(span.recovered).toBe(true);
    expect(span.ms).toBe(7 * 60 * 1000);
    expect(span.recoveryEventId).toBe("taskcontroller_evt_4");
  });

  it("reports an unrecovered failure as ms null, never zero", () => {
    const events = richStream().slice(0, 4); // failure, no recovery
    const m = recoveryProfile(events);
    const span = m.value![0];
    expect(span.recovered).toBe(false);
    expect(span.ms).toBeNull();
  });

  it("returns null when there is no failure at all", () => {
    const m = recoveryProfile([ev(0, "run_started"), ev(1, "run_completed")]);
    expect(m.value).toBeNull();
    expect(m.incomplete).toContain("NO_MATCHING_EVENTS");
  });

  it("does not pair a failure with a different target's recovery", () => {
    const events = [
      ev(0, "gate_failed", { gate: "G3" }),
      ev(1, "gate_passed", { gate: "G4" }),
    ];
    const span = recoveryProfile(events).value![0];
    expect(span.recovered).toBe(false);
  });
});

describe("handoff derivation (acceptance 5)", () => {
  it("derives actor-to-actor handoffs with timing", () => {
    const m = handoffProfile(richStream());
    const pairs = m.value!.map((h) => `${h.fromActor}->${h.toActor}`);
    expect(pairs).toContain("ChatGPT TaskController->Human");
    expect(pairs).toContain("Human->Hermes Mac");
    expect(m.value!.every((h) => h.ms !== null)).toBe(true);
  });

  it("does not report a handoff when the actor is unchanged", () => {
    const m = handoffProfile([
      ev(0, "run_started", { actor: "same" }),
      ev(1, "node_progress", { node_id: "M4", actor: "same" }),
    ]);
    expect(m.value).toEqual([]);
  });

  it("never invents a participant from an unknown actor", () => {
    const m = handoffProfile([
      ev(0, "run_started", { actor: "A" }),
      ev(1, "node_progress", { node_id: "M4" }), // no actor -> UNKNOWN
      ev(2, "run_completed", { actor: "A" }),
    ]);
    expect(m.value).toEqual([]);
    expect(m.incomplete).toContain("NO_MATCHING_EVENTS");
  });

  it("supports structured actor objects", () => {
    const m = handoffProfile([
      ev(0, "run_started", { actor: { kind: "agent", id: "hermes" } }),
      ev(1, "run_completed", { actor: { kind: "human", id: "nhat" } }),
    ]);
    expect(m.value![0].fromActor).toBe("agent:hermes");
    expect(m.value![0].toActor).toBe("human:nhat");
  });
});

describe("trace-back to exact refs (acceptance 2)", () => {
  it("traceOf carries source identity, evidence and authority", () => {
    const t = traceOf(
      ev(4, "gate_passed", {
        gate: "G3",
        evidence_refs: ["ci://run/2"],
        authority_ref: "G3-R1",
      })
    );
    expect(t.sourceEventId).toBe("taskcontroller_evt_4");
    expect(t.sequence).toBe(4);
    expect(t.evidenceRefs).toEqual(["ci://run/2"]);
    expect(t.authorityRef).toBe("G3-R1");
  });

  it("every computed aggregate carries a non-empty trace", () => {
    const events = richStream();
    for (const m of [
      runDuration(events),
      longestWait(events),
      retryProfile(events),
      recoveryProfile(events),
      handoffProfile(events),
    ]) {
      expect(m.value).not.toBeNull();
      expect(m.trace.length).toBeGreaterThan(0);
    }
  });

  it("recovery trace includes both the failure and the recovery event", () => {
    const ids = recoveryProfile(richStream()).trace.map((t) => t.sourceEventId);
    expect(ids).toContain("taskcontroller_evt_3");
    expect(ids).toContain("taskcontroller_evt_4");
  });

  it("retry trace references every counted attempt", () => {
    const ids = retryProfile(richStream()).trace.map((t) => t.sourceEventId);
    expect(ids).toContain("taskcontroller_evt_3");
    expect(ids).toContain("taskcontroller_evt_4");
  });

  it("evidence refs on a trace come only from the source event", () => {
    const t = recoveryProfile(richStream()).trace.find(
      (x) => x.sourceEventId === "taskcontroller_evt_4"
    );
    expect(t?.evidenceRefs).toEqual(["ci://run/2"]);
  });
});

describe("report + incomplete marking (acceptance 1 & 3)", () => {
  it("produces a reproducible report", () => {
    const a = reviewRun("RUN-M4", richStream());
    const b = reviewRun("RUN-M4", richStream());
    expect(a).toEqual(b);
    expect(a.reducerVersion).toBe(REDUCER_VERSION);
  });

  it("never claims governance authority", () => {
    expect(reviewRun("RUN-M4", richStream()).createsAuthority).toBe(false);
  });

  it("marks a complete history as complete", () => {
    const r = reviewRun("RUN-M4", richStream());
    expect(r.historyComplete).toBe(true);
    expect(r.incompleteMarkers).toEqual([]);
  });

  it("visibly marks incomplete history", () => {
    const r = reviewRun("RUN-M4", richStream().slice(0, 3));
    expect(r.historyComplete).toBe(false);
    expect(r.incompleteMarkers).toContain("UNTERMINATED");
  });

  it("marks anomalies present when the stream has them", () => {
    const dup = ev(1, "node_progress", { node_id: "M4" });
    const r = reviewRun("RUN-M4", [ev(0, "run_started"), dup, dup, ev(2, "run_completed")]);
    expect(r.anomalyCount).toBeGreaterThan(0);
    expect(r.incompleteMarkers).toContain("ANOMALIES_PRESENT");
    expect(r.historyComplete).toBe(false);
  });

  it("handles an empty run without inventing metrics", () => {
    const r = reviewRun("RUN-EMPTY", []);
    expect(r.eventCount).toBe(0);
    expect(r.duration.value).toBeNull();
    expect(r.incompleteMarkers).toContain("NO_EVENTS");
  });
});

describe("compare-runs version guard (acceptance 4)", () => {
  it("compares two compatible complete runs", () => {
    const left = reviewRun("A", richStream());
    const slower = richStream().map((e) =>
      e.source_event_id === "taskcontroller_evt_6"
        ? ({ ...e, occurred_at: "2026-08-23T10:30:00Z" } as ProjectionEvent)
        : e
    );
    const right = reviewRun("B", slower);
    const cmp = compareRuns(left, right);
    expect(cmp.comparable).toBe(true);
    expect(cmp.warnings).toEqual([]);
    expect(cmp.deltas["duration.totalMs"]).toBe(14 * 60 * 1000);
    expect(cmp.deltas["eventCount"]).toBe(0);
  });

  it("warns and suppresses deltas on reducer-version mismatch", () => {
    const left = reviewRun("A", richStream());
    const right = { ...reviewRun("B", richStream()), reducerVersion: "other/9" };
    const cmp = compareRuns(left, right);
    expect(cmp.comparable).toBe(false);
    expect(cmp.warnings).toContain("REDUCER_VERSION_MISMATCH");
    expect(cmp.deltas).toEqual({});
  });

  it("warns and suppresses deltas on schema-version mismatch", () => {
    const left = reviewRun("A", richStream());
    const right = { ...reviewRun("B", richStream()), schemaVersion: "2" };
    const cmp = compareRuns(left, right);
    expect(cmp.comparable).toBe(false);
    expect(cmp.warnings).toContain("SCHEMA_VERSION_MISMATCH");
  });

  it("warns on incomplete history but still compares", () => {
    const left = reviewRun("A", richStream());
    const right = reviewRun("B", richStream().slice(0, 3));
    const cmp = compareRuns(left, right);
    expect(cmp.comparable).toBe(true);
    expect(cmp.warnings).toContain("INCOMPLETE_HISTORY");
  });

  it("warns when either side carries anomalies", () => {
    const dup = ev(1, "node_progress", { node_id: "M4" });
    const cmp = compareRuns(
      reviewRun("A", richStream()),
      reviewRun("B", [ev(0, "run_started"), dup, dup, ev(2, "run_completed")])
    );
    expect(cmp.warnings).toContain("ANOMALIES_PRESENT");
  });

  it("returns a null delta when one side is not computable", () => {
    const cmp = compareRuns(reviewRun("A", richStream()), reviewRun("B", []));
    expect(cmp.deltas["duration.totalMs"]).toBeNull();
  });
});
