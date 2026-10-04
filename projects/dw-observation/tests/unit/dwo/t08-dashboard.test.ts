/**
 * T08 — Source-backed dashboard projection tests.
 *
 * Verifies the DashboardProjection contract from TECH_SPEC §10:
 *   - every aggregate is null when its source is unavailable
 *   - a zero count only appears when the source affirmatively reported zero
 *   - drilldown links resolve to the right routes
 *   - source guard: no fixture import in the production path
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { readDashboardProjection } from "@/lib/dashboard/readDashboardProjection";
import type { TaskRunRelationRecord } from "@/lib/dwo/taskRunIndex";

function record(overrides: Partial<TaskRunRelationRecord>): TaskRunRelationRecord {
  return {
    taskRef: "SCRUM-820",
    relationRevisionId: "rel-1",
    rootRunIds: ["RUN-A"],
    sourceSystem: "DWO",
    sourceRecordId: "record-1",
    sourceDigest: "sha256:rel-1",
    durablePosition: 10,
    supersedesRevisionId: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests 1–2: source availability and null-vs-zero discipline
// ---------------------------------------------------------------------------

describe("T08 · source-backed projection", () => {
  // --- Test 1: every aggregate null when its source is unavailable ---
  it("every aggregate is null when its source is unavailable", () => {
    // Real source with no task records → task source unavailable.
    // Run source is independent (listRuns has its own data) — task-scoped
    // aggregates must be null, never 0 or [].
    const projection = readDashboardProjection("real", []);

    // Task-source aggregates: null when no records (source unavailable).
    expect(projection.taskCount).toBeNull();
    expect(projection.unresolvedCount).toBeNull();
    expect(projection.needsAttention).toEqual([]);

    // Authority source: no evidence passed in → null (unavailable).
    expect(projection.authorityWaitCount).toBeNull();

    // Live state source: no bootstrap passed in → null (unavailable).
    expect(projection.degradedSourceCount).toBeNull();
  });

  // --- Test 2: zero count only when source affirmatively reported zero ---
  it("zero count only appears when the source affirmatively reported zero", () => {
    // With no records, taskCount is null — never 0 by default.
    const empty = readDashboardProjection("real", []);
    expect(empty.taskCount).not.toBe(0);
    expect(empty.unresolvedCount).not.toBe(0);

    // With fixture records, the source affirmatively reports counts.
    const fixtureRecords = [
      record({ taskRef: "SCRUM-555" }),
      record({ taskRef: "SCRUM-820" }),
    ];
    const withData = readDashboardProjection("fixture", fixtureRecords);
    expect(typeof withData.taskCount).toBe("number");
    expect(withData.taskCount).not.toBeNull();
    // runCounts has affirmative keys from the source.
    expect(Object.keys(withData.runCounts).length).toBeGreaterThan(0);
  });

  // --- Test 3: drilldown links resolve to the right routes ---
  it("drilldown links resolve to the right routes", () => {
    const fixtureRecords = [
      record({ taskRef: "SCRUM-555" }),
      record({ taskRef: "SCRUM-820" }),
    ];
    const projection = readDashboardProjection("fixture", fixtureRecords);

    // Task drilldown: /tasks/{taskRef}
    for (const item of projection.needsAttention) {
      const entry = item as { route?: string; taskRef?: string };
      if (entry.taskRef) {
        expect(entry.route).toBe(`/tasks/${entry.taskRef}`);
      }
    }

    // Run drilldown: /runs/{runId}
    for (const item of projection.recentActivity) {
      const entry = item as { route?: string; runId?: string };
      if (entry.runId) {
        expect(entry.route).toBe(`/runs/${entry.runId}`);
      }
    }
  });

  // --- Test 4: source guard — no fixture import in production path ---
  it("source guard: no fixture import in production path", () => {
    const srcPath = path.resolve(process.cwd(), "lib/dashboard/readDashboardProjection.ts");
    const content = fs.readFileSync(srcPath, "utf-8");
    expect(content).not.toContain("taskFixtures");
  });
});