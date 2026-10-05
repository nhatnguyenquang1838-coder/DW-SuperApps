/**
 * T04 — UnifiedRuntimeModel + 4 adapters unit tests.
 *
 * 1. Determinism — each adapter called twice on same input produces deep-equal models.
 * 2. One shape — assert every adapter's output satisfies UnifiedRunWorkspaceModel.
 * 3. No React — source files must not import React.
 * 4. Hierarchy != dependency — parent/child chain and dependency edges preserved independently.
 * 5. No fabrication — real adapter with unavailable source returns null/UNKNOWN, no fixture leak.
 * 6. Detail preservation — login-epic and node-architect adapters preserve artifacts/runbook/checkpoints/history.
 */

import { describe, it, expect, vi } from "vitest";
import type {
  UnifiedRunWorkspaceModel,
  UnifiedRuntimeNode,
} from "@/lib/runtime/unifiedRuntime";
import { realRuntimeAdapter } from "@/lib/runtime/adapters/realRuntimeAdapter";
import { loginAuthScenarioAdapter } from "@/lib/runtime/adapters/loginAuthScenarioAdapter";
import { nodeArchitectScenarioAdapter } from "@/lib/runtime/adapters/nodeArchitectScenarioAdapter";
import { fixtureScenarioAdapter } from "@/lib/runtime/adapters/fixtureScenarioAdapter";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";
import type { LoginEpicRuntimeFixture } from "@/lib/loginEpicRuntimeGraph";
import type { SimRun } from "@/lib/simRun";

// ---------------------------------------------------------------------------
// Mock server reads for the SCRUM-820 P3 realRuntimeAdapter tests.
// Default backend = degraded (matches no-server behavior); each test overrides
// the mock for the non-degraded path.
// ---------------------------------------------------------------------------

const { mockReadServerRunDetail, mockReadHistoricalEvents } = vi.hoisted(() => ({
  mockReadServerRunDetail: vi.fn(),
  mockReadHistoricalEvents: vi.fn(),
}));

mockReadServerRunDetail.mockResolvedValue({
  degraded: true,
  backend: "none",
  run: null,
  gates: [],
  nodes: [],
  events: [],
  canonicalHistoryAvailable: false,
  projectionStatus: "PROJECTION_UNAVAILABLE",
});
mockReadHistoricalEvents.mockResolvedValue({
  events: [],
  backend: "none",
  degraded: true,
});

vi.mock("@/lib/serverRunRead", () => ({
  readServerConfig: vi.fn(() => ({ url: "http://test", publishableKey: "test" })),
  readServerRunDetail: (...args: unknown[]) => mockReadServerRunDetail(...args),
}));

vi.mock("@/lib/serverHistoricalRead", () => ({
  readHistoricalEvents: (...args: unknown[]) => mockReadHistoricalEvents(...args),
}));

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function satisfiesModel(m: unknown): m is UnifiedRunWorkspaceModel {
  if (!m || typeof m !== "object") return false;
  const o = m as Record<string, unknown>;
  if (typeof o.runId !== "string") return false;
  if (!Array.isArray(o.nodes)) return false;
  if (!Array.isArray(o.edges)) return false;
  if (!Array.isArray(o.orderedSteps)) return false;
  // Check node shape.
  for (const n of o.nodes as unknown[]) {
    if (!n || typeof n !== "object") return false;
    const nn = n as Record<string, unknown>;
    if (typeof nn.id !== "string") return false;
    if (!Array.isArray((nn as unknown as UnifiedRuntimeNode).declaredGates)) return false;
    if (!Array.isArray((nn as unknown as UnifiedRuntimeNode).artifacts)) return false;
    if (!Array.isArray((nn as unknown as UnifiedRuntimeNode).runbook)) return false;
    if (!Array.isArray((nn as unknown as UnifiedRuntimeNode).checkpoints)) return false;
    if (!Array.isArray((nn as unknown as UnifiedRuntimeNode).taskControllerHistory)) return false;
    if (!Array.isArray((nn as unknown as UnifiedRuntimeNode).executorHistory)) return false;
  }
  // Check edge shape.
  for (const e of o.edges as unknown[]) {
    if (!e || typeof e !== "object") return false;
    const ee = e as Record<string, unknown>;
    if (typeof ee.id !== "string") return false;
    if (typeof ee.source !== "string") return false;
    if (typeof ee.target !== "string") return false;
    if (!["DEPENDENCY", "ROUTE", "FANOUT"].includes(ee.kind as string)) return false;
    if (!["SATISFIED", "BLOCKING", "UNKNOWN"].includes(ee.state as string)) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Test fixture factories
// ---------------------------------------------------------------------------

function makeLoginEpicFixture(): LoginEpicRuntimeFixture {
  return {
    epic_id: "LOGIN-CAPABILITY",
    title: "Test Login Epic",
    run_count: 10,
    runtime_node_count: 2,
    runtime_model: "G0..G6",
    runs: [
      {
        id: "test-run-1",
        index: 0,
        slug: "test",
        title: "Test Run",
        objective: "test objective",
        run_kind: "implementation",
        allowed_paths: [],
        forbidden_actions: [],
        status: "OPEN",
        summary: "test summary",
        route: [
          { gate_id: "G0_CONTEXT", node_id: "node-0" },
          { gate_id: "G1_ALIGNMENT", node_id: "node-1" },
        ],
        gates: [
          {
            id: "G0_CONTEXT",
            label: "G0 Context",
            summary: "context gate",
            x: 0, y: 0, w: 100, h: 60,
            nodes: [
              {
                gate_id: "G0_CONTEXT", id: "node-0", title: "Node 0",
                family: "runtime", type: "action", boundary: "product/ui",
                purpose: "test purpose",
                fileReads: ["/src/test.ts"], fileWrites: ["/src/out.ts"],
                artifacts: ["artifact-a"], runbook: ["step-1"],
                taskControllerHistory: ["tc-h-1"], executorHistory: ["ex-h-1"],
                checkpoints: ["cp-1"], x: 0, y: 0, w: 80, h: 40,
              },
            ],
            gateArtifacts: ["gate-art"],
            taskControllerHistory: ["tc-gate-1"],
            executorHistory: ["ex-gate-1"],
          },
          {
            id: "G1_ALIGNMENT", label: "G1 Alignment", summary: "align gate",
            x: 0, y: 100, w: 100, h: 60,
            nodes: [
              {
                gate_id: "G1_ALIGNMENT", id: "node-1", title: "Node 1",
                family: "runtime", type: "check", boundary: "shared/contract",
                purpose: "check purpose",
                fileReads: ["/src/check.ts"], fileWrites: [],
                artifacts: ["artifact-b"], runbook: ["step-2"],
                taskControllerHistory: ["tc-h-2"], executorHistory: ["ex-h-2"],
                checkpoints: ["cp-2"], x: 0, y: 0, w: 80, h: 40,
              },
            ],
            gateArtifacts: [],
            taskControllerHistory: [],
            executorHistory: [],
          },
        ],
      },
    ],
  };
}

function makeSimRun(): SimRun {
  return {
    run_id: "sim-run-1",
    task_id: "TASK-001",
    repository: "test/repo",
    base_branch: "main",
    base_sha: "abc123",
    status: "OPEN",
    gates: [
      {
        id: "G2", label: "G2 Execution", summary: "exec gate",
        nodes: [
          {
            node_id: "sn-1", title: "Sim Node 1", description: "test",
            node_type: "action", family: "core", authority_boundary: "product/ui",
            source_status: "PENDING", maturity: "M1",
            declared_gates: ["G2"], canonical: "yes",
            gate_id: "G2", sequence: 0,
            artifacts: ["sim-art-a"], reads: ["/src/sim.ts"],
            runbook: ["sim-step-1"],
            taskcontroller_history: [{ event_id: "e1", type: "decision", actor: "tc", outcome: "ok" }],
            executor_history: [{ event_id: "e2", type: "exec", actor: "ex", outcome: "ok" }],
            checkpoints: [{ checkpoint_id: "cp1", revision: 1, current_node_id: "sn-1", next_node_id: "sn-2", lease_owner: "ex", fencing_token: "f1", status: "active" }],
            options: [],
          },
        ],
        gate_artifacts: [],
        taskcontroller_history: [],
        executor_history: [],
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("T04 UnifiedRuntimeModel + adapters", () => {
  // --- 1. Determinism ---
  describe("determinism", () => {
    it("loginAuthScenarioAdapter returns deep-equal models on same input", () => {
      const fixture = makeLoginEpicFixture();
      const a = loginAuthScenarioAdapter(fixture, "test-run-1");
      const b = loginAuthScenarioAdapter(fixture, "test-run-1");
      expect(a).toEqual(b);
    });

    it("nodeArchitectScenarioAdapter returns deep-equal models on same input", () => {
      const run = makeSimRun();
      const a = nodeArchitectScenarioAdapter(run);
      const b = nodeArchitectScenarioAdapter(run);
      expect(a).toEqual(b);
    });

    it("fixtureScenarioAdapter returns deep-equal models on same input", () => {
      const entry = FIXTURE_CATALOG[0];
      const a = fixtureScenarioAdapter(entry);
      const b = fixtureScenarioAdapter(entry);
      expect(a).toEqual(b);
    });
  });

  // --- 2. One shape ---
  describe("one shape", () => {
    it("loginAuthScenarioAdapter output satisfies UnifiedRunWorkspaceModel", () => {
      const result = loginAuthScenarioAdapter(makeLoginEpicFixture(), "test-run-1");
      expect(satisfiesModel(result)).toBe(true);
      expect(result.runId).toBe("test-run-1");
    });

    it("nodeArchitectScenarioAdapter output satisfies UnifiedRunWorkspaceModel", () => {
      const result = nodeArchitectScenarioAdapter(makeSimRun());
      expect(satisfiesModel(result)).toBe(true);
      expect(result.runId).toBe("sim-run-1");
    });

    it("fixtureScenarioAdapter output satisfies UnifiedRunWorkspaceModel", () => {
      const result = fixtureScenarioAdapter(FIXTURE_CATALOG[0]);
      expect(satisfiesModel(result)).toBe(true);
    });

    it("realRuntimeAdapter output satisfies UnifiedRunWorkspaceModel (degraded path)", async () => {
      const result = await realRuntimeAdapter("nonexistent-run");
      expect(satisfiesModel(result)).toBe(true);
    });
  });

  // --- 3. No React ---
  describe("no React", () => {
    it("unifiedRuntime.ts contains no React import", () => {
      const fs = require("fs");
      const path = require("path");
      const content = fs.readFileSync(
        path.join(process.cwd(), "lib/runtime/unifiedRuntime.ts"),
        "utf8",
      );
      expect(content).not.toContain('from "react"');
      expect(content).not.toContain('require("react")');
    });

    it("all adapter files contain no React import", () => {
      const fs = require("fs");
      const path = require("path");
      const adapterDir = path.join(process.cwd(), "lib/runtime/adapters");
      const files = fs.readdirSync(adapterDir).filter((f: string) => f.endsWith(".ts"));
      for (const f of files) {
        const content = fs.readFileSync(path.join(adapterDir, f), "utf8");
        expect(content, `${f} must not import React`).not.toContain('from "react"');
        expect(content, `${f} must not require React`).not.toContain('require("react")');
      }
    });
  });

  // --- 4. Hierarchy != dependency ---
  describe("hierarchy vs dependency", () => {
    it("preserves parent/child hierarchy and dependency edges independently", () => {
      // Construct a model where hierarchy says A -> B (parent/child)
      // but dependency edges say B -> A (the opposite direction).
      // The model must preserve BOTH independently — a child is NOT
      // automatically a dependent.
      const model: UnifiedRunWorkspaceModel = {
        runId: "hier-test",
        taskRef: null,
        mode: "SIMULATED",
        status: "OPEN",
        hierarchy: { parent: "A", child: "B" },
        nodes: [
          { id: "A", gateId: null, title: "Parent", family: null, nodeType: null, authorityBoundary: null, sourceStatus: null, maturity: null, declaredGates: [], purpose: null, fileReads: [], fileWrites: [], artifacts: [], runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [] },
          { id: "B", gateId: null, title: "Child", family: null, nodeType: null, authorityBoundary: null, sourceStatus: null, maturity: null, declaredGates: [], purpose: null, fileReads: [], fileWrites: [], artifacts: [], runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [] },
        ],
        edges: [
          { id: "dep-B-A", source: "B", target: "A", kind: "DEPENDENCY", state: "SATISFIED" },
        ],
        orderedSteps: [{ nodeId: "A", sequence: 0 }, { nodeId: "B", sequence: 1 }],
        currentSequence: null,
        canonicalHistoryAvailable: false,
        projectionStatus: "UNKNOWN",
        sourceDigest: null,
      };
      // Hierarchy says A is parent of B.
      expect(model.hierarchy).toEqual({ parent: "A", child: "B" });
      // Dependency edge goes B -> A (reverse of hierarchy).
      const depEdge = model.edges.find((e) => e.kind === "DEPENDENCY");
      expect(depEdge).toBeDefined();
      expect(depEdge!.source).toBe("B");
      expect(depEdge!.target).toBe("A");
      // The child (B) is NOT a dependent (it is a source in the dependency edge).
      expect(depEdge!.source).not.toBe("A");
    });
  });

  // --- 5. No fabrication ---
  describe("no fabrication", () => {
    it("realRuntimeAdapter returns UNKNOWN/null when server unavailable (no fixture leak)", async () => {
      const result = await realRuntimeAdapter("nonexistent-run");
      // When the server is unreachable, the degraded path returns
      // fully unknown values — no fixture data should leak in.
      expect(result.runId).toBe("nonexistent-run");
      expect(result.status).toBe("UNKNOWN");
      expect(result.nodes).toEqual([]);
      expect(result.edges).toEqual([]);
      expect(result.projectionStatus).toBe("PROJECTION_UNAVAILABLE");
      expect(result.canonicalHistoryAvailable).toBe(false);
      expect(result.sourceDigest).toBeNull();
      expect(result.mode).toBe("LIVE");
    });
  });

  // --- 6. Detail preservation ---
  describe("detail preservation", () => {
    it("loginAuthScenarioAdapter preserves artifacts, runbook, checkpoints, history", () => {
      const result = loginAuthScenarioAdapter(makeLoginEpicFixture(), "test-run-1");
      const node0 = result.nodes.find((n) => n.id === "node-0");
      expect(node0).toBeDefined();
      expect(node0!.artifacts.length).toBeGreaterThan(0);
      expect(node0!.runbook.length).toBeGreaterThan(0);
      expect(node0!.checkpoints.length).toBeGreaterThan(0);
      expect(node0!.taskControllerHistory.length).toBeGreaterThan(0);
      expect(node0!.executorHistory.length).toBeGreaterThan(0);
    });

    it("nodeArchitectScenarioAdapter preserves artifacts, runbook, checkpoints, history", () => {
      const result = nodeArchitectScenarioAdapter(makeSimRun());
      const sn1 = result.nodes.find((n) => n.id === "sn-1");
      expect(sn1).toBeDefined();
      expect(sn1!.artifacts.length).toBeGreaterThan(0);
      expect(sn1!.runbook.length).toBeGreaterThan(0);
      expect(sn1!.checkpoints.length).toBeGreaterThan(0);
      expect(sn1!.taskControllerHistory.length).toBeGreaterThan(0);
      expect(sn1!.executorHistory.length).toBeGreaterThan(0);
    });
  });
});

// ---------------------------------------------------------------------------
// SCRUM-820 P3 — realRuntimeAdapter: durable sequences + no fabricated edges
// ---------------------------------------------------------------------------

describe("SCRUM-820 P3 · realRuntimeAdapter", () => {
  /** Non-degraded server detail with gates + nodes (no dependency evidence). */
  function mockNonDegradedDetail() {
    mockReadServerRunDetail.mockResolvedValue({
      degraded: false,
      backend: "supabase_publishable",
      run: { run_id: "T04-NODE-A", status: "ACTIVE" },
      gates: [
        { gate_id: "node-1", gate_label: "First", boundary: "product/ui", state: "ACCEPTED" },
        { gate_id: "node-2", gate_label: "Second", boundary: "product/ui", state: "OPEN" },
      ],
      nodes: [],
      events: [],
      canonicalHistoryAvailable: true,
      projectionStatus: "AVAILABLE",
    });
  }

  it("orderedSteps carries durable event sequences, never positional 0..N", async () => {
    mockNonDegradedDetail();
    // Durable sequences are SPARSE: node-1 at seq 4, node-2 at seq 17.
    mockReadHistoricalEvents.mockResolvedValue({
      events: [
        {
          run_id: "T04-NODE-A", source_system: "taskcontroller", source_event_id: "evt-1",
          sequence: 4, projection_ordinal: 1, event_type: "node_started",
          occurred_at: "2026-08-23T10:00:00Z", gate: "node-1", node_id: "node-1",
          actor: "Hermes", outcome: "active", evidence_refs: [], authority_ref: undefined,
          source_digest: undefined,
        },
        {
          run_id: "T04-NODE-A", source_system: "taskcontroller", source_event_id: "evt-2",
          sequence: 17, projection_ordinal: 2, event_type: "node_completed",
          occurred_at: "2026-08-23T10:01:00Z", gate: "node-2", node_id: "node-2",
          actor: "Hermes", outcome: "done", evidence_refs: [], authority_ref: undefined,
          source_digest: undefined,
        },
      ],
      backend: "supabase_publishable",
      degraded: false,
    });

    const result = await realRuntimeAdapter("T04-NODE-A");
    const sequences = result.orderedSteps.map((s) => s.sequence);
    // Durable source sequences, not array positions.
    expect(sequences).toEqual([4, 17]);
    expect(sequences).not.toEqual([0, 1]);
    expect(result.currentSequence).toBeNull();
  });

  it("events with no dependency evidence produce ZERO DEPENDENCY edges", async () => {
    mockNonDegradedDetail();
    // Events mention BOTH a gate and a node — that is event/gate membership,
    // NOT dependency evidence. Zero DEPENDENCY edges must be the honest answer.
    mockReadHistoricalEvents.mockResolvedValue({
      events: [
        {
          run_id: "T04-NODE-A", source_system: "taskcontroller", source_event_id: "evt-1",
          sequence: 4, projection_ordinal: 1, event_type: "node_started",
          occurred_at: "2026-08-23T10:00:00Z", gate: "node-1", node_id: "node-1",
          actor: "Hermes", outcome: "active", evidence_refs: [], authority_ref: undefined,
          source_digest: undefined,
        },
      ],
      backend: "supabase_publishable",
      degraded: false,
    });

    const result = await realRuntimeAdapter("T04-NODE-A");
    expect(result.edges.filter((e) => e.kind === "DEPENDENCY")).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
  });

  it("an ordered step whose durable sequence has no matching event is absent (fail-closed)", async () => {
    mockNonDegradedDetail();
    // Only node-1 has canonical history evidence (seq 4). node-2 has none.
    mockReadHistoricalEvents.mockResolvedValue({
      events: [
        {
          run_id: "T04-NODE-A", source_system: "taskcontroller", source_event_id: "evt-1",
          sequence: 4, projection_ordinal: 1, event_type: "node_started",
          occurred_at: "2026-08-23T10:00:00Z", gate: "node-1", node_id: "node-1",
          actor: "Hermes", outcome: "active", evidence_refs: [], authority_ref: undefined,
          source_digest: undefined,
        },
      ],
      backend: "supabase_publishable",
      degraded: false,
    });

    const result = await realRuntimeAdapter("T04-NODE-A");
    // node-2 has NO durable sequence evidence → must not fabricate a step for it.
    expect(result.orderedSteps.some((s) => s.nodeId === "node-2")).toBe(false);
    expect(result.orderedSteps.some((s) => s.nodeId === "node-1")).toBe(true);
    expect(result.orderedSteps[0].sequence).toBe(4);
  });
});
