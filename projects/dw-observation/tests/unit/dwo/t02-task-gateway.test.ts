/**
 * T02 — Canonical Task read gateway tests.
 *
 * RED phase: these tests fail until lib/taskTypes.ts and lib/taskRead.ts
 * are implemented. They assert the gateway contracts from the SCRUM-820
 * T02 spec.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  readFixtureSummaries,
  readRealSummaries,
  resolveTask,
} from "@/lib/taskRead";
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

describe("T02 · task gateway", () => {
  // --- Test 1: RESOLVED for a known task ---
  it("returns RESOLVED for a task the canonical source knows", () => {
    const summaries = readFixtureSummaries();
    const sc555 = summaries.find((s) => s.taskRef === "SCRUM-555");
    expect(sc555).toBeDefined();
    expect(sc555!.status).toBe("RESOLVED");
    expect(sc555!.rootRunCount).toBe(1);
    expect(sc555!.relationRevision).toBe(1);
  });

  // --- Test 2: UNAVAILABLE when real source unavailable, NOT from fixtures ---
  it("returns UNAVAILABLE when the real source has no records, not fixtures", async () => {
    const result = await resolveTask("SCRUM-820", "real", []);
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.rootRunCount).toBeNull();
    // Fixtures must NOT have been used: if they were, status would be UNKNOWN_UNRESOLVED
    expect(result.status).not.toBe("UNKNOWN_UNRESOLVED");
  });

  // --- Test 3: UNKNOWN_UNRESOLVED for unresolvable relation ---
  it("returns UNKNOWN_UNRESOLVED when the relation cannot be established", () => {
    const summaries = readFixtureSummaries();
    const sc820 = summaries.find((s) => s.taskRef === "SCRUM-820");
    expect(sc820).toBeDefined();
    expect(sc820!.status).toBe("UNKNOWN_UNRESOLVED");
    expect(sc820!.rootRunCount).toBeNull();
  });

  // --- Test 4: CONFLICT when sources disagree at same revision ---
  it("returns CONFLICT when real and fixture sources disagree at the same revision", async () => {
    // Fixture: SCRUM-820 at rel-1 with RUN-A
    const fixtureRecords: TaskRunRelationRecord[] = [
      record({
        taskRef: "SCRUM-820",
        relationRevisionId: "rel-1",
        rootRunIds: ["RUN-A"],
        sourceRecordId: "fixture-1",
      }),
    ];
    // Real: SCRUM-820 at rel-1 with RUN-B — disagrees
    const realRecords: TaskRunRelationRecord[] = [
      record({
        taskRef: "SCRUM-820",
        relationRevisionId: "rel-1",
        rootRunIds: ["RUN-B"],
        sourceRecordId: "real-1",
      }),
    ];

    const result = await resolveTask("SCRUM-820", "fixture", realRecords, fixtureRecords);
    expect(result.status).toBe("CONFLICT");
  });

  // --- Test 5: Regression guard — page.tsx does not import taskFixtures ---
  it("regression guard: app/tasks/page.tsx does not import from taskFixtures", () => {
    const pagePath = path.resolve(process.cwd(), "app/tasks/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    expect(content).not.toContain("taskFixtures");
  });

  // --- Test 6: rootRunCount stays null when unknown, never 0 ---
  it("rootRunCount is null when unknown, never 0 by default", () => {
    const summaries = readFixtureSummaries();
    const sc820 = summaries.find((s) => s.taskRef === "SCRUM-820");
    expect(sc820).toBeDefined();
    expect(sc820!.rootRunCount).toBeNull();
    // Defensive: explicitly not 0
    expect(sc820!.rootRunCount).not.toBe(0);
  });
});