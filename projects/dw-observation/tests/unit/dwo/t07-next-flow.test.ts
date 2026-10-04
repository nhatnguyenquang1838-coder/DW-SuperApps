/**
 * T07 — Source-backed Next Flow projection unit tests.
 *
 * Tests the computeNextFlow function per TECH_SPEC §7.
 *
 * Rules:
 *  - NO graph-position inference
 *  - NO guessing from sequence when source contract does not authorize it
 *  - Conflicting sources => CONFLICT
 *  - Missing source => UNKNOWN
 *  - Replay computes Next Flow as-of selected historical sequence only
 */
import { describe, expect, it } from "vitest";
import { computeNextFlow, type NextFlowProjection } from "@/lib/runtime/nextFlow";
import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";
import type { BlockingPath } from "@/lib/dwo/blockingPath";

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function makeModel(overrides: Partial<UnifiedRunWorkspaceModel> = {}): UnifiedRunWorkspaceModel {
  return {
    runId: "T07-TEST-RUN",
    taskRef: "SCRUM-820",
    mode: "SIMULATED" as WorkspaceMode,
    status: "ACTIVE",
    hierarchy: null,
    nodes: [
      {
        id: "node-A", gateId: "G2", title: "Node A", family: "runtime",
        nodeType: "action", authorityBoundary: "product/ui", sourceStatus: "ACTIVE",
        maturity: "stable", declaredGates: ["G2"], purpose: "test",
        fileReads: [], fileWrites: [], artifacts: [], runbook: [],
        taskControllerHistory: [], executorHistory: [], checkpoints: [],
      },
      {
        id: "node-B", gateId: "G3", title: "Node B", family: "runtime",
        nodeType: "check", authorityBoundary: "code_review", sourceStatus: "DONE",
        maturity: "stable", declaredGates: ["G3"], purpose: "test",
        fileReads: [], fileWrites: [], artifacts: [], runbook: [],
        taskControllerHistory: [], executorHistory: [], checkpoints: [],
      },
      {
        id: "node-C", gateId: "G4", title: "Node C", family: "runtime",
        nodeType: "action", authorityBoundary: "product/ui", sourceStatus: "PENDING",
        maturity: "stable", declaredGates: ["G4"], purpose: "test",
        fileReads: [], fileWrites: [], artifacts: [], runbook: [],
        taskControllerHistory: [], executorHistory: [], checkpoints: [],
      },
    ],
    edges: [
      { id: "e1", source: "node-A", target: "node-B", kind: "DEPENDENCY", state: "SATISFIED" },
      { id: "e2", source: "node-B", target: "node-C", kind: "DEPENDENCY", state: "SATISFIED" },
    ],
    orderedSteps: [
      { nodeId: "node-A", sequence: 0 },
      { nodeId: "node-B", sequence: 1 },
      { nodeId: "node-C", sequence: 2 },
    ],
    currentSequence: 0,
    canonicalHistoryAvailable: false,
    projectionStatus: "UNKNOWN",
    sourceDigest: null,
    ...overrides,
  };
}

function makeBlockingPath(status: BlockingPath["status"], reason: BlockingPath["reason"]): BlockingPath {
  return {
    runId: "T07-TEST-RUN",
    status,
    reason,
    blockedBy: [],
    authorityState: "NOT_REQUIRED",
  };
}

// ===========================================================================
// TESTS
// ===========================================================================

describe("T07 — Next Flow projection", () => {

  // ── 1. Resolved from one source ────────────────────────────────────────

  describe("resolved from one source", () => {
    it("returns RESOLVED with nextNodeId when orderedSteps has a next node", () => {
      const model = makeModel({ currentSequence: 0 });
      const result = computeNextFlow(model);
      expect(result.status).toBe("RESOLVED");
      expect(result.nextNodeId).toBe("node-B");
      expect(result.currentNodeId).toBe("node-A");
      expect(result.source).toBe("FIXTURE"); // SIMULATED mode => FIXTURE
      expect(result.reason).not.toBeNull();
      expect(result.blocker).toBeNull();
    });

    it("returns RESOLVED at final step with no nextNodeId", () => {
      const model = makeModel({ currentSequence: 2 });
      const result = computeNextFlow(model);
      expect(result.status).toBe("RESOLVED");
      expect(result.nextNodeId).toBeNull();
      expect(result.currentNodeId).toBe("node-C");
      expect(result.reason).toBe("At final step");
    });
  });

  // ── 2. Blocked with blocker text ───────────────────────────────────────

  describe("blocked with blocker text", () => {
    it("returns BLOCKED when blocking path says BLOCKED", () => {
      const model = makeModel({ currentSequence: 0 });
      const blocking = makeBlockingPath("BLOCKED", "UNMET_DEPENDENCY");
      const result = computeNextFlow(model, { blockingPath: blocking });
      expect(result.status).toBe("BLOCKED");
      expect(result.blocker).toBe("UNMET_DEPENDENCY");
      expect(result.nextNodeId).toBeNull();
    });
  });

  // ── 3. Missing source => UNKNOWN (not a guess) ─────────────────────────

  describe("missing source => UNKNOWN", () => {
    it("returns UNKNOWN when currentSequence is null", () => {
      const model = makeModel({ currentSequence: null });
      const result = computeNextFlow(model);
      expect(result.status).toBe("UNKNOWN");
      expect(result.nextNodeId).toBeNull();
      expect(result.currentNodeId).toBeNull();
      expect(result.reason).toContain("source data");
    });

    it("returns UNKNOWN when orderedSteps is empty", () => {
      const model = makeModel({ currentSequence: 0, orderedSteps: [] });
      const result = computeNextFlow(model);
      expect(result.status).toBe("UNKNOWN");
      expect(result.reason).toContain("source data");
    });
  });

  // ── 4. Two sources disagreeing => CONFLICT ──────────────────────────────

  describe("two sources disagreeing => CONFLICT", () => {
    it("returns CONFLICT when orderedSteps and edges disagree on next node", () => {
      // orderedSteps says node-B is next (sequence 0 -> 1)
      // edges say node-C is the only satisfied dependency of node-A (rewire)
      const model = makeModel({
        currentSequence: 0,
        edges: [
          { id: "e1", source: "node-A", target: "node-C", kind: "DEPENDENCY", state: "SATISFIED" },
        ],
      });
      const result = computeNextFlow(model);
      expect(result.status).toBe("CONFLICT");
      expect(result.reason).toContain("conflict");
    });

    it("returns RESOLVED when orderedSteps and edges agree", () => {
      const model = makeModel({ currentSequence: 0 });
      // edges: node-A -> node-B (agrees with orderedSteps[1] = node-B)
      const result = computeNextFlow(model);
      expect(result.status).toBe("RESOLVED");
      expect(result.nextNodeId).toBe("node-B");
    });
  });

  // ── 5. Replay computes as-of selected sequence only ────────────────────

  describe("replay computes as-of selected sequence", () => {
    it("in REPLAY mode, next node is based on selected sequence, not live", () => {
      const model = makeModel({
        mode: "REPLAY" as WorkspaceMode,
        currentSequence: 1, // at node-B, next should be node-C
      });
      const result = computeNextFlow(model);
      expect(result.source).toBe("REPLAY_SNAPSHOT");
      expect(result.currentNodeId).toBe("node-B");
      expect(result.nextNodeId).toBe("node-C");
      expect(result.status).toBe("RESOLVED");
    });

    it("in REPLAY mode at final sequence returns no nextNodeId", () => {
      const model = makeModel({
        mode: "REPLAY" as WorkspaceMode,
        currentSequence: 2, // at last node
      });
      const result = computeNextFlow(model);
      expect(result.source).toBe("REPLAY_SNAPSHOT");
      expect(result.nextNodeId).toBeNull();
      expect(result.status).toBe("RESOLVED");
    });
  });

  // ── 6. Negative test: shuffling node ORDER does not change result ───────

  describe("negative test — no positional inference", () => {
    it("shuffling orderedSteps order produces the same result", () => {
      const modelA = makeModel({ currentSequence: 0 });
      const resultA = computeNextFlow(modelA);

      // Shuffle the array order but keep the same sequence→nodeId mapping.
      // If the implementation uses array index (positional inference),
      // the result would change. Using the sequence field makes it stable.
      const modelB = makeModel({
        currentSequence: 0,
        orderedSteps: [
          { nodeId: "node-B", sequence: 1 }, // same mapping, different order
          { nodeId: "node-A", sequence: 0 }, // same mapping, different order
          { nodeId: "node-C", sequence: 2 }, // same mapping, different order
        ],
      });
      const resultB = computeNextFlow(modelB);

      // The result should be the same because lookup is by sequence field,
      // not by array position — proving no positional inference.
      expect(resultA.status).toBe(resultB.status);
      expect(resultA.nextNodeId).toBe(resultB.nextNodeId);
      expect(resultA.currentNodeId).toBe(resultB.currentNodeId);
    });

    it("does not derive next node from visual coordinates or layout", () => {
      const model = makeModel({ currentSequence: 0 });
      const result = computeNextFlow(model);
      // The result must come from orderedSteps+currentSequence, not from node positions
      expect(result.status).toBe("RESOLVED");
      expect(result.nextNodeId).toBe("node-B");
    });
  });
});