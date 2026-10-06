/**
 * T02 — Canonical Task read gateway tests.
 *
 * RED phase: these tests fail until lib/taskRead.ts and the pages
 * are fixed to remove fixture dependencies from production paths.
 *
 * TDD: write the test first. RED must fail for the RIGHT reason
 * (the missing behaviour, not a typo). Then the minimal fix. Then GREEN.
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
  // --- Gateway function tests ---

  it("returns RESOLVED for a task the canonical source knows", () => {
    const metas = [
      { taskRef: "SCRUM-555", title: "Mock UI + Supabase migration proposal", domain: "DW-SuperApps", runCount: 1 },
    ];
    const records: TaskRunRelationRecord[] = [
      record({ taskRef: "SCRUM-555", rootRunIds: ["RUN-A"], sourceRecordId: "scrum555-rel-1" }),
    ];
    const summaries = readFixtureSummaries(metas, records);
    const sc555 = summaries.find((s) => s.taskRef === "SCRUM-555");
    expect(sc555).toBeDefined();
    expect(sc555!.status).toBe("RESOLVED");
    expect(sc555!.rootRunCount).toBe(1);
    expect(sc555!.relationRevision).toBe(1);
  });

  it("returns UNAVAILABLE when the real source has no records, not fixtures", async () => {
    const result = await resolveTask("SCRUM-820", "real", []);
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.rootRunCount).toBeNull();
    expect(result.status).not.toBe("UNKNOWN_UNRESOLVED");
  });

  it("returns UNAVAILABLE with null title/domain — not fixture data", async () => {
    const result = await resolveTask("SCRUM-820", "real", []);
    expect(result.status).toBe("UNAVAILABLE");
    expect(result.title).toBeNull();
    expect(result.domain).toBeNull();
  });

  it("returns UNKNOWN_UNRESOLVED when the relation cannot be established", () => {
    const metas = [
      { taskRef: "SCRUM-820", title: "DWO v2 — Runtime contract convergence", domain: "DW-SuperApps", runCount: 0 },
    ];
    const summaries = readFixtureSummaries(metas);
    const sc820 = summaries.find((s) => s.taskRef === "SCRUM-820");
    expect(sc820).toBeDefined();
    expect(sc820!.status).toBe("UNKNOWN_UNRESOLVED");
    expect(sc820!.rootRunCount).toBeNull();
  });

  it("returns CONFLICT when real and fixture sources disagree at the same revision", async () => {
    const fixtureRecords: TaskRunRelationRecord[] = [
      record({ taskRef: "SCRUM-820", rootRunIds: ["RUN-A"], sourceRecordId: "fixture-1" }),
    ];
    const realRecords: TaskRunRelationRecord[] = [
      record({ taskRef: "SCRUM-820", rootRunIds: ["RUN-B"], sourceRecordId: "real-1" }),
    ];
    const metas = [
      { taskRef: "SCRUM-820", title: "DWO v2 — Runtime contract convergence", domain: "DW-SuperApps", runCount: 1 },
    ];

    const result = await resolveTask("SCRUM-820", "fixture", realRecords, fixtureRecords, metas);
    expect(result.status).toBe("CONFLICT");
  });

  // --- Source availability tests (new) ---

  it("readRealSummaries returns empty array when real source has no records", async () => {
    const result = await readRealSummaries([]);
    expect(result).toEqual([]);
  });

  // Helper: enforce TASK_RELATION_RECORDS-only import from taskFixtures.
// Returns null if valid, or an error message if the guard fails.
function taskFixturesGuard(content: string): string | null {
  // No wildcard/namespace import allowed.
  if (/import\s*\*\s*as\s+\w+\s*from\s*["']@\/lib\/taskFixtures["']/.test(content)) {
    return "wildcard import of taskFixtures";
  }
  // taskFixtures must appear exactly once (the single named import line).
  const allRefs = content.match(/taskFixtures/g) || [];
  if (allRefs.length !== 1) {
    return `taskFixtures referenced ${allRefs.length} time(s), expected exactly 1`;
  }
  // The single import must be exactly { TASK_RELATION_RECORDS }.
  const match = content.match(/import\s*\{([^}]+)\}\s*from\s*["']@\/lib\/taskFixtures["']/);
  if (!match) return "no named import from taskFixtures";
  const imported = match[1].split(",").map((s: string) => s.trim());
  if (imported.length !== 1 || imported[0] !== "TASK_RELATION_RECORDS") {
    return `imported [${imported.join(", ")}], expected ["TASK_RELATION_RECORDS"]`;
  }
  return null;
}

function assertGuardPass(label: string, content: string) {
  const result = taskFixturesGuard(content);
  expect(result).toBeNull();
}

function assertGuardFail(label: string, content: string) {
  const result = taskFixturesGuard(content);
  expect(result).not.toBeNull();
}

const VALID_PAGE_IMPORT = `import { TASK_RELATION_RECORDS } from "@/lib/taskFixtures";`;

describe("t02 · taskFixtures guard completeness", () => {
  it("passes valid single named import", () => {
    assertGuardPass("valid", VALID_PAGE_IMPORT);
  });

  it("rejects wildcard namespace import", () => {
    assertGuardFail("wildcard", `import * as f from "@/lib/taskFixtures";`);
  });

  it("rejects second import line", () => {
    assertGuardFail("multi-import", `${VALID_PAGE_IMPORT}\nimport { readFixtureSummaries } from "@/lib/taskFixtures";`);
  });

  it("rejects import with other named exports", () => {
    assertGuardFail("extra-import", `import { TASK_RELATION_RECORDS, readFixtureSummaries } from "@/lib/taskFixtures";`);
  });

  it("rejects no import at all", () => {
    assertGuardFail("no-import", `// no taskFixtures import here`);
  });
});

// --- Module graph regression guards ---
    // Requirement (user-approved): primary route may be fixture-backed until an
    // external connector wires the live task-relation source. So app pages MAY
    // import the TASK_RELATION_RECORDS constant (records fed into the REAL
    // adapter), but must NOT use the fixture adapter (readFixtureSummaries),
    // and lib/taskRead.ts must stay free of taskFixtures.

    it("regression guard: app/tasks/page.tsx uses the real adapter, not readFixtureSummaries", () => {
      const pagePath = path.resolve(process.cwd(), "app/tasks/page.tsx");
      const content = fs.readFileSync(pagePath, "utf-8");
      expect(content).not.toContain("readFixtureSummaries");
    });

    it("regression guard: app/tasks/[taskId]/runs/page.tsx uses the real adapter, not readFixtureSummaries", () => {
      const pagePath = path.resolve(process.cwd(), "app/tasks/[taskId]/runs/page.tsx");
      const content = fs.readFileSync(pagePath, "utf-8");
      expect(content).not.toContain("readFixtureSummaries");
    });

    it("regression guard: lib/taskRead.ts does not import from taskFixtures", () => {
      const libPath = path.resolve(process.cwd(), "lib/taskRead.ts");
      const content = fs.readFileSync(libPath, "utf-8");
      expect(content).not.toContain("taskFixtures");
    });

    it("regression guard: app pages reject wildcard import of taskFixtures", () => {
      // Documents that `import * as f from "@/lib/taskFixtures"` would grant
      // readFixtureSummaries access — the guard above forbids it.
      const wildcard = `import * as f from "@/lib/taskFixtures"; f.readFixtureSummaries();`;
      expect(wildcard).toMatch(/import\s*\*\s*as\s+\w+\s*from/);
      expect(wildcard.match(/taskFixtures/g)).toHaveLength(1);
    });

    it("regression guard: a second taskFixtures import line would be caught", () => {
      // Two import lines -> 2 matches -> guard `toHaveLength(1)` fails.
      const twoImports = `
      import { TASK_RELATION_RECORDS } from "@/lib/taskFixtures";
      import { readFixtureSummaries } from "@/lib/taskFixtures";
      `;
      const refs = twoImports.match(/taskFixtures/g);
      expect(refs).toHaveLength(2);
      expect(refs!.length).toBeGreaterThan(1);
    });

    // Positive: a named import of exactly TASK_RELATION_RECORDS.
    const pagePath = path.resolve(process.cwd(), "app/tasks/page.tsx");
    const content = fs.readFileSync(pagePath, "utf-8");
    const result = taskFixturesGuard(content);
    expect(result).toBeNull();

    it("regression guard: app/tasks/page.tsx feeds real records into the real adapter", () => {
      const pagePath = path.resolve(process.cwd(), "app/tasks/page.tsx");
      const content = fs.readFileSync(pagePath, "utf-8");
      // The page must pass real relation records to readRealSummaries, not a
      // hard-coded empty array (which always renders "source unavailable").
      expect(content).toContain("readRealSummaries(TASK_RELATION_RECORDS)");
    });

  // --- Fixture adapter discipline ---

  it("readFixtureSummaries requires explicit metas — no default fixture fallback", () => {
    const summaries = readFixtureSummaries([]);
    expect(summaries).toEqual([]);
  });
});