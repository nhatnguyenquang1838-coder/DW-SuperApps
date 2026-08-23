import { describe, it, expect } from "vitest";
import { simRunG0G6 } from "@/fixtures/simRunG0G6";
import {
  buildTimeline,
  clampCursor,
  getGate,
  getNode,
  activeGateIdAt,
  isGateActiveAt,
  nodeStateAt,
  selectedNodeAt,
  timelineLength,
} from "@/lib/simRun";

const RUN = simRunG0G6;

describe("simRun (corrected node-architect model)", () => {
  it("exposes 7 gates and 54 runtime node cards", () => {
    expect(RUN.gates).toHaveLength(7);
    const total = RUN.gates.reduce((n, g) => n + g.nodes.length, 0);
    expect(total).toBe(54);
  });

  it("derives a 54-step replay timeline ordered by node.sequence", () => {
    const tl = buildTimeline(RUN);
    expect(tl).toHaveLength(54);
    const seqs = tl.map((s) => s.sequence);
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b));
    // first node is G0 intake_context.source-resolution, last is G6 unknown-write-reconciliation
    expect(tl[0]).toMatchObject({
      gate_id: "G0_CONTEXT",
      node_id: "intake_context.source-resolution",
    });
    expect(tl[53]).toMatchObject({
      gate_id: "G6_PRODUCTION_DATA",
      node_id: "failure_recovery.unknown-write-reconciliation",
    });
  });

  it("nodeStateAt is done/active/future relative to cursor", () => {
    // assign gate families per corrected architect
    expect(nodeStateAt(RUN, "G0_CONTEXT", "intake_context.source-resolution", 0)).toBe(
      "active",
    );
    expect(nodeStateAt(RUN, "G0_CONTEXT", "intake_context.source-resolution", 5)).toBe(
      "done",
    );
    expect(nodeStateAt(RUN, "G6_PRODUCTION_DATA", "lifecycle.g6-production-approval", 0)).toBe(
      "future",
    );
  });

  it("activeGateIdAt / isGateActiveAt track the cursor's gate", () => {
    expect(activeGateIdAt(RUN, 0)).toBe("G0_CONTEXT");
    expect(isGateActiveAt(RUN, "G0_CONTEXT", 0)).toBe(true);
    expect(isGateActiveAt(RUN, "G2_EXECUTION", 0)).toBe(false);
    // G2 starts at sequence 19 -> index 18
    expect(activeGateIdAt(RUN, 18)).toBe("G2_EXECUTION");
  });

  it("getGate / getNode resolve by id", () => {
    expect(getGate(RUN, "G0_CONTEXT")?.label).toContain("Context");
    expect(
      getNode(RUN, "G2_EXECUTION", "package-export-governance-tree-build")?.family,
    ).toBe("package_export");
  });

  it("selectedNodeAt falls back to the cursor's node", () => {
    const sel = selectedNodeAt(RUN, 10);
    expect(sel).toEqual({
      kind: "node",
      gateId: "G1_ALIGNMENT",
      nodeId: "gate_authority.evidence-artifact-map",
    });
  });

  it("clampCursor keeps cursor within [0, len-1]", () => {
    expect(clampCursor(RUN, -5)).toBe(0);
    expect(clampCursor(RUN, 999)).toBe(53);
    expect(clampCursor(RUN, 20)).toBe(20);
    expect(timelineLength(RUN)).toBe(54);
  });
});
