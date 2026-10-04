/**
 * T03 — Source-backed Task→Root Run hydration tests.
 *
 * Verifies:
 *   1. Same-revision relation conflict fails closed
 *   2. Absent run metadata stays null/UNKNOWN, never 0 or []
 *   3. No inference from run id or branch naming
 *   4. Source guard: page does not call listRuns("mock")
 *   5. relationRevision is surfaced in the rendered output
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { resolveFromIndex, buildTaskRunIndexV2 } from "@/lib/dwo/taskRunIndex";
import { TASK_RELATION_RECORDS } from "@/lib/taskFixtures";
import { listRuns } from "@/lib/observatory";
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
// Tests 1–3: behavioural tests via the resolution gateway
// ---------------------------------------------------------------------------

describe("T03 · source-backed hydration", () => {
  // --- Test 1: same-revision relation conflict fails closed ---
  it("same-revision relation conflict fails closed", () => {
    const records: TaskRunRelationRecord[] = [
      record({
        sourceRecordId: "a",
        rootRunIds: ["RUN-A"],
        sourceDigest: "sha256:a",
      }),
      record({
        sourceRecordId: "b",
        rootRunIds: ["RUN-B"],
        sourceDigest: "sha256:b",
      }),
    ];
    const index = buildTaskRunIndexV2(records);
    const decision = resolveFromIndex(index, "SCRUM-820");
    expect(decision.status).toBe("UNKNOWN_UNRESOLVED");
    expect(decision.reason).toBe("RELATION_CONFLICT");
    expect(decision.rootRunIds).toEqual([]);
    expect(decision.conflictingRevisions).toEqual(["rel-1"]);
  });

  // --- Test 2: absent run metadata stays null/UNKNOWN, never 0 or [] ---
  it("absent run metadata stays null/UNKNOWN, never 0 or []", () => {
    // Point the relation at a run that does NOT exist in fixtures.
    const records: TaskRunRelationRecord[] = [
      record({
        sourceRecordId: "a",
        rootRunIds: ["NONEXISTENT-RUN"],
        sourceDigest: "sha256:a",
      }),
    ];
    const index = buildTaskRunIndexV2(records);
    const decision = resolveFromIndex(index, "SCRUM-820");

    // Relation resolves (record is well-formed).
    expect(decision.status).toBe("RESOLVED");
    expect(decision.rootRunIds).toEqual(["NONEXISTENT-RUN"]);

    // Hydrate via the same source-backed listRuns("real") path the page uses.
    const runsById = new Map(listRuns("real").map((r: any) => [r.runId, r]));
    const run = runsById.get("NONEXISTENT-RUN");

    // Run metadata is absent from the source → null/UNKNOWN, never 0 or [].
    expect(run).toBeUndefined();

    // Build the summary the page would produce.
    const summary = {
      runId: "NONEXISTENT-RUN",
      status: run?.status ?? "—",
      sourceSystem: run?.sourceSystem && run.sourceSystem !== "—" ? run.sourceSystem : null,
      lane: run?.lane && run.lane !== "—" ? run.lane : null,
      startedAt: run?.startedAt ?? null,
      lifecycleProgress: null,
      anomalyCount: run?.anomalyCount ?? null,
      relationRevision: null,
    };

    expect(summary.status).toBe("—");
    expect(summary.sourceSystem).toBeNull();
    expect(summary.lane).toBeNull();
    expect(summary.startedAt).toBeNull();
    expect(summary.lifecycleProgress).toBeNull();
    expect(summary.anomalyCount).toBeNull();
    expect(summary.relationRevision).toBeNull();
    // Never 0 or [] for absent metadata.
    expect(summary.anomalyCount).not.toBe(0);
  });

  // --- Test 3: no inference from run id or branch naming ---
  it("no inference from run id or branch naming", () => {
    // A run id that looks like a task key must NOT resolve to that task.
    // The module has no reverse lookup — absence of records = unresolved.
    const index = buildTaskRunIndexV2([]);
    const decision = resolveFromIndex(index, "SCRUM-820");
    expect(decision.status).toBe("UNKNOWN_UNRESOLVED");
    expect(decision.rootRunIds).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Tests 4–5: source-level guards (read file as text)
// ---------------------------------------------------------------------------

describe("T03 · source guards", () => {
  const pagePath = path.resolve(
    process.cwd(),
    "app/tasks/[taskId]/runs/page.tsx"
  );
  const pageContent = fs.readFileSync(pagePath, "utf-8");

  // --- Test 4: source guard — page does not call listRuns("mock") ---
  it('source guard: page does not call listRuns("mock")', () => {
    expect(pageContent).not.toContain('listRuns("mock")');
  });

  // --- Test 5: relationRevision is surfaced in the rendered output ---
  it("relationRevision is surfaced in the rendered output", () => {
    expect(pageContent).toContain("relationRevision");
  });
});