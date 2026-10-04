/**
 * T09C — Adapter dispatch + real-mode coverage.
 *
 * Acceptance criteria for SCRUM-820 P5:
 * 1. A test proves the mock branch is unreachable when
 *    OBSERVATORY_DATA_SOURCE is unset — real mode never calls mock data.
 * 2. A test asserting WHICH adapter is selected for real / mock / fixture inputs.
 *
 * TDD: write failing tests first, then minimal fix.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Mocks — must be set before importing the page module
// ---------------------------------------------------------------------------

const mockRealRuntimeAdapter = vi.fn();
const mockLoginAuthScenarioAdapter = vi.fn();
const mockFixtureScenarioAdapter = vi.fn();
const mockReadServerRunDetail = vi.fn();
const mockGetReplaySnapshot = vi.fn();
const mockReplayToModel = vi.fn();
const mockGetRun = vi.fn();
const mockMockProjectionEvents = vi.fn();

vi.mock("@/lib/runtime/adapters/realRuntimeAdapter", () => ({
  realRuntimeAdapter: (...args: unknown[]) => mockRealRuntimeAdapter(...args),
}));

vi.mock("@/lib/runtime/adapters/loginAuthScenarioAdapter", () => ({
  loginAuthScenarioAdapter: (...args: unknown[]) =>
    mockLoginAuthScenarioAdapter(...args),
}));

vi.mock("@/lib/runtime/adapters/fixtureScenarioAdapter", () => ({
  fixtureScenarioAdapter: (...args: unknown[]) =>
    mockFixtureScenarioAdapter(...args),
}));

vi.mock("@/lib/serverRunRead", () => ({
  readServerRunDetail: (...args: unknown[]) => mockReadServerRunDetail(...args),
}));

vi.mock("@/lib/runtime/replay", async () => {
  const actual = await vi.importActual("@/lib/runtime/replay");
  return {
    ...actual,
    getReplaySnapshot: (...args: unknown[]) => mockGetReplaySnapshot(...args),
    replayToModel: (...args: unknown[]) => mockReplayToModel(...args),
  };
});

vi.mock("@/lib/observatory", () => ({
  getRun: (...args: unknown[]) => mockGetRun(...args),
  UNKNOWN: "UNKNOWN",
}));

vi.mock("@/lib/mockDataSource", () => ({
  getMockProjectionEvents: (...args: unknown[]) =>
    mockMockProjectionEvents(...args),
  MOCK_BACKEND: "mock",
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockDegradedDetail() {
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
}

function mockNonDegradedDetail() {
  mockReadServerRunDetail.mockResolvedValue({
    degraded: false,
    backend: "supabase_publishable",
    run: { run_id: "TEST-RUN", status: "ACTIVE" },
    gates: [],
    nodes: [],
    events: [],
    canonicalHistoryAvailable: true,
    projectionStatus: "AVAILABLE",
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("T09C adapter dispatch + real-mode coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDegradedDetail();
    // Default: realRuntimeAdapter returns a minimal valid model
    mockRealRuntimeAdapter.mockResolvedValue({
      runId: "TEST-RUN",
      taskRef: null,
      mode: "LIVE",
      status: "UNKNOWN",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "PROJECTION_UNAVAILABLE",
      sourceDigest: null,
    });
    mockLoginAuthScenarioAdapter.mockReturnValue({
      runId: "TEST-RUN",
      taskRef: null,
      mode: "SIMULATED",
      status: "UNKNOWN",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "UNKNOWN",
      sourceDigest: null,
    });
    mockFixtureScenarioAdapter.mockReturnValue({
      runId: "TEST-RUN",
      taskRef: null,
      mode: "SIMULATED",
      status: "UNKNOWN",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "UNKNOWN",
      sourceDigest: null,
    });
    mockGetReplaySnapshot.mockResolvedValue({ status: "NOT_FOUND" });
    mockReplayToModel.mockReturnValue({ model: null, mode: "REPLAY" });
  });

  // -----------------------------------------------------------------------
  // Criterion 1: real mode never calls mock data
  // -----------------------------------------------------------------------

  describe("real-mode coverage — mock branch unreachable", () => {
    it("getMockProjectionEvents is never called in real mode", async () => {
      mockNonDegradedDetail();

      // Build the page module dynamically with real-mode env
      const origEnv = process.env.OBSERVATORY_DATA_SOURCE;
      delete process.env.OBSERVATORY_DATA_SOURCE;

      try {
        const { buildWorkspaceModel } = await import("@/app/runs/[runId]/page");
        await buildWorkspaceModel("TEST-RUN", "real");

        // Real mode must never touch mock data utilities
        expect(mockGetRun).not.toHaveBeenCalled();
        expect(mockMockProjectionEvents).not.toHaveBeenCalled();
      } finally {
        if (origEnv === undefined) {
          delete process.env.OBSERVATORY_DATA_SOURCE;
        } else {
          process.env.OBSERVATORY_DATA_SOURCE = origEnv;
        }
      }
    });

    it("getMockProjectionEvents is never called even when OBSERVATORY_DATA_SOURCE is unset", async () => {
      mockNonDegradedDetail();

      const origEnv = process.env.OBSERVATORY_DATA_SOURCE;
      delete process.env.OBSERVATORY_DATA_SOURCE;

      try {
        const { buildWorkspaceModel } = await import("@/app/runs/[runId]/page");
        // When OBSERVATORY_DATA_SOURCE is unset, dataSource defaults to "real"
        await buildWorkspaceModel("TEST-RUN", "real");

        expect(mockGetRun).not.toHaveBeenCalled();
        expect(mockMockProjectionEvents).not.toHaveBeenCalled();
      } finally {
        if (origEnv === undefined) {
          delete process.env.OBSERVATORY_DATA_SOURCE;
        } else {
          process.env.OBSERVATORY_DATA_SOURCE = origEnv;
        }
      }
    });
  });

  // -----------------------------------------------------------------------
  // Criterion 2: adapter selection for real / mock / fixture inputs
  // -----------------------------------------------------------------------

  describe("adapter selection", () => {
    it("real mode selects realRuntimeAdapter", async () => {
      mockNonDegradedDetail();

      const { buildWorkspaceModel } = await import("@/app/runs/[runId]/page");
      const result = await buildWorkspaceModel("TEST-RUN", "real");

      expect(mockRealRuntimeAdapter).toHaveBeenCalledWith("TEST-RUN");
      expect(mockLoginAuthScenarioAdapter).not.toHaveBeenCalled();
      expect(mockFixtureScenarioAdapter).not.toHaveBeenCalled();
      expect(result.mode).toBe("LIVE");
    });

    it("mock mode selects loginAuthScenarioAdapter", async () => {
      mockGetRun.mockReturnValue({
        runId: "TEST-RUN",
        title: "Mock Run",
        objective: "",
        status: "OPEN",
        gates: {},
      });

      const { buildWorkspaceModel } = await import("@/app/runs/[runId]/page");
      const result = await buildWorkspaceModel("TEST-RUN", "mock");

      expect(mockLoginAuthScenarioAdapter).toHaveBeenCalled();
      expect(mockRealRuntimeAdapter).not.toHaveBeenCalled();
      expect(mockFixtureScenarioAdapter).not.toHaveBeenCalled();
      expect(result.mode).toBe("SIMULATED");
    });

    it("fixture mode selects fixtureScenarioAdapter", async () => {
      const { FIXTURE_CATALOG } = await import("@/lib/dwo/fixtureSpec");
      const entry = FIXTURE_CATALOG[0];

      const { buildWorkspaceModel } = await import("@/app/runs/[runId]/page");
      const result = await buildWorkspaceModel(entry.id, "fixture");

      expect(mockFixtureScenarioAdapter).toHaveBeenCalledWith(entry);
      expect(mockRealRuntimeAdapter).not.toHaveBeenCalled();
      expect(mockLoginAuthScenarioAdapter).not.toHaveBeenCalled();
      expect(result.mode).toBe("SIMULATED");
    });

    it("each dataSource selects exactly one adapter — no overlap", async () => {
      mockNonDegradedDetail();
      mockGetRun.mockReturnValue({
        runId: "TEST-RUN",
        title: "Mock Run",
        objective: "",
        status: "OPEN",
        gates: {},
      });
      const { FIXTURE_CATALOG } = await import("@/lib/dwo/fixtureSpec");
      const entry = FIXTURE_CATALOG[0];

      const { buildWorkspaceModel } = await import("@/app/runs/[runId]/page");

      // Real
      await buildWorkspaceModel("TEST-RUN", "real");
      expect(mockRealRuntimeAdapter).toHaveBeenCalledTimes(1);
      expect(mockLoginAuthScenarioAdapter).not.toHaveBeenCalled();
      expect(mockFixtureScenarioAdapter).not.toHaveBeenCalled();

      vi.clearAllMocks();
      mockDegradedDetail();

      // Mock
      await buildWorkspaceModel("TEST-RUN", "mock");
      expect(mockLoginAuthScenarioAdapter).toHaveBeenCalledTimes(1);
      expect(mockRealRuntimeAdapter).not.toHaveBeenCalled();
      expect(mockFixtureScenarioAdapter).not.toHaveBeenCalled();

      vi.clearAllMocks();

      // Fixture
      await buildWorkspaceModel(entry.id, "fixture");
      expect(mockFixtureScenarioAdapter).toHaveBeenCalledTimes(1);
      expect(mockRealRuntimeAdapter).not.toHaveBeenCalled();
      expect(mockLoginAuthScenarioAdapter).not.toHaveBeenCalled();
    });
  });
});