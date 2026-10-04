/**
 * T08-replay — replayToModel SCRUM-820 P3 unit tests.
 *
 * 1. orderedSteps carries durable sequence ids, never 0..N.
 * 2. selected sequence with no matching step → PROJECTION_UNAVAILABLE.
 * 3. Events with no dependency evidence → ZERO DEPENDENCY edges.
 */

import { describe, it, expect } from "vitest";
import { replayToModel } from "@/lib/runtime/replay";
import type { ReplayProjection } from "@/lib/runtime/unifiedRuntime";

function makeProjection(overrides: Partial<ReplayProjection> = {}): ReplayProjection {
  return {
    runId: "REPLAY-TEST-RUN",
    startedAt: null,
    lastEventAt: null,
    events: [],
    nodes: {},
    gates: {},
    anomalies: [],
    ...overrides,
  };
}

// ===========================================================================
// Tests
// ===========================================================================

describe("T08-replay · replayToModel", () => {
  it("orderedSteps carries durable event sequences, never positional 0..N", () => {
    // Node-A last event seq 4, Node-B last event seq 17 (sparse, not 0..N).
    const projection = makeProjection({
      nodes: {
        "node-A": { node: "node-A", status: "active", lastEventSeq: 4 },
        "node-B": { node: "node-B", status: "done", lastEventSeq: 17 },
      },
    });

    const result = replayToModel(projection, 17, "REPLAY");

    const sequences = result.model.orderedSteps.map((s) => s.sequence);
    expect(sequences).toEqual([4, 17]);
    expect(sequences).not.toEqual([0, 1]);
  });

  it("selected sequence with no matching step yields PROJECTION_UNAVAILABLE", () => {
    // Only node-A exists (seq 4). selectedSequence=50 has no step.
    const projection = makeProjection({
      nodes: {
        "node-A": { node: "node-A", status: "active", lastEventSeq: 4 },
      },
    });

    const result = replayToModel(projection, 50, "REPLAY");

    expect(result.status).toBe("PROJECTION_UNAVAILABLE");
    expect(result.projection).toBeNull();
    expect(result.model).toBeNull();
  });

  it("events with no dependency evidence produce ZERO DEPENDENCY edges", () => {
    // Events mention gate+node (membership) — NOT dependency evidence.
    // Must produce ZERO DEPENDENCY edges.
    const projection = makeProjection({
      nodes: {
        "node-A": { node: "node-A", status: "active", lastEventSeq: 4 },
      },
      events: [
        {
          run_id: "R1",
          source_system: "taskcontroller",
          source_event_id: "evt-1",
          sequence: 4,
          projection_ordinal: 1,
          event_type: "node_started",
          occurred_at: "2026-08-23T10:00:00Z",
          gate: "node-A",
          node_id: "node-A",
          actor: "Hermes",
          outcome: "active",
          evidence_refs: [],
          authority_ref: undefined,
          source_digest: undefined,
        },
      ],
    });

    const result = replayToModel(projection, 4, "REPLAY");

    expect(result.model.edges.filter((e) => e.kind === "DEPENDENCY")).toHaveLength(0);
    expect(result.model.edges).toHaveLength(0);
  });

  it("selectedSequence null → currentSequence is null", () => {
    const projection = makeProjection({
      nodes: {
        "node-A": { node: "node-A", status: "active", lastEventSeq: 4 },
      },
    });

    const result = replayToModel(projection, null, "REPLAY");

    expect(result.model.currentSequence).toBeNull();
  });
});
