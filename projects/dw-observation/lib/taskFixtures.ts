/**
 * CR-826-C — Task → Root-run relation fixtures for /tasks navigation.
 *
 * SCRAM-826 / DWO-V2-05, G2 EXECUTE, PLAN-826-R1, child run CR-826-C.
 *
 * Read-only fixture bundle for the Task-first entry. Mirrors the same
 * no-inference contract as lib/dwo/taskRunIndex.ts: taskRef is read from
 * the record, never derived from run-id/name/branch patterns.
 *
 * These records are development-only seeds for local review. They carry
 * explicit digests so the resolution path (resolveFromIndex) exercises its
 * full supression/conflict logic identically to production data.
 */
import type { TaskRunRelationRecord } from "./dwo/taskRunIndex";
import { buildTaskRunIndexV2, resolveFromIndex } from "./dwo/taskRunIndex";

/** Canonical task refs for the review fixture pack. */
export const SCRUM_555 = "SCRUM-555";
export const SCRUM_820 = "SCRUM-820";

/**
 * Authoritative relation records. Each task points to its root runs via
 * an explicit, digest-pinned record — never inferred.
 */
export const TASK_RELATION_RECORDS: readonly TaskRunRelationRecord[] = [
  {
    taskRef: SCRUM_555,
    relationRevisionId: "rel-1",
    rootRunIds: ["DW-OBS-M5-20260823-MOCK"],
    sourceSystem: "DWO",
    sourceRecordId: "scrum555-rel-1",
    sourceDigest: "sha256:scrum555-rel-1",
    durablePosition: 100,
    supersedesRevisionId: null,
  },
];

/**
 * Build a TaskRunIndexV2 from the fixture records.
 * Re-exports the real resolver so /tasks uses the exact same path as production.
 */
export function buildTaskIndex() {
  const index = buildTaskRunIndexV2(TASK_RELATION_RECORDS);
  return {
    index,
    resolve: (taskRef: string) => resolveFromIndex(index, taskRef),
  };
}

/** Task metadata for listing. */
export interface TaskMeta {
  taskRef: string;
  title: string;
  domain: string;
  runCount: number;
}

export const TASK_META: readonly TaskMeta[] = [
  {
    taskRef: SCRUM_555,
    title: "DW Observation M5 — Mock UI + Supabase migration proposal",
    domain: "DW-SuperApps",
    runCount: 1,
  },
  {
    taskRef: SCRUM_820,
    title: "DWO v2 — Runtime contract convergence",
    domain: "DW-SuperApps",
    runCount: 0, // no relation record yet → unresolved
  },
];

/**
 * Resolve a task's root runs through the real TaskRunIndexV2 resolver.
 * Returns empty [] when no relation record exists (fail-closed, no inference).
 */
export function getTaskRootRuns(taskRef: string): {
  status: "RESOLVED" | "UNKNOWN_UNRESOLVED";
  reason: string;
  rootRunIds: readonly string[];
} {
  const index = buildTaskRunIndexV2(TASK_RELATION_RECORDS);
  const decision = resolveFromIndex(index, taskRef);
  return {
    status: decision.status,
    reason: decision.reason,
    rootRunIds: decision.rootRunIds,
  };
}

export const TASK_FIXTURES_CAPABILITIES = {
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const;
