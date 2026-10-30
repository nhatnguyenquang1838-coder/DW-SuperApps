import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  readFixtureSummaries,
  readRealSummaries,
  resolveTask,
  type TaskMeta,
} from "@/lib/taskRead";
import type { TaskRunRelationRecord } from "@/lib/dwo/taskRunIndex";

function record(overrides: Partial<TaskRunRelationRecord> = {}): TaskRunRelationRecord {
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

const metadata: TaskMeta[] = [
  { taskRef: "SCRUM-555", title: "Fixture task", domain: "DWO", runCount: 1 },
];

describe("T02 · canonical Task read gateway", () => {
  it("keeps the explicit fixture adapter available for isolated development tests", () => {
    const result = readFixtureSummaries(metadata, [
      record({ taskRef: "SCRUM-555", sourceRecordId: "fixture-relation" }),
    ]);
    expect(result[0]?.status).toBe("RESOLVED");
    expect(result[0]?.rootRunIds).toEqual(["RUN-A"]);
  });

  it("does not represent an absent real source as an empty healthy task set", async () => {
    expect(await readRealSummaries([])).toEqual([]);
  });

  it("never falls back to fixture records when the selected source is real", async () => {
    const fixtureRecords = [record({ taskRef: "SCRUM-555" })];
    const result = await resolveTask("SCRUM-555", "real", [], fixtureRecords, metadata);
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.rootRunCount).toBeNull();
    expect(result.title).toBeNull();
  });

  it("fails closed on same-revision disagreement", async () => {
    const taskMetadata = [
      { taskRef: "SCRUM-820", title: "DWO v2", domain: "DWO", runCount: 1 },
    ];
    const result = await resolveTask(
      "SCRUM-820",
      "real",
      [record({ rootRunIds: ["RUN-REAL"] })],
      [record({ rootRunIds: ["RUN-FIXTURE"] })],
      taskMetadata,
    );
    expect(result.status).toBe("CONFLICT");
    expect(result.rootRunCount).toBeNull();
  });

  it("keeps fixture modules out of primary real Task routes", () => {
    const files = ["app/tasks/page.tsx", "app/tasks/[taskId]/runs/page.tsx"];
    for (const file of files) {
      const content = fs.readFileSync(path.resolve(process.cwd(), file), "utf8");
      expect(content).not.toMatch(/from\s+["']@\/lib\/taskFixtures["']/);
      expect(content).not.toMatch(/\b(TASK_RELATION_RECORDS|TASK_META|getTaskRootRuns|readFixtureSummaries)\b/);
    }
  });
});
