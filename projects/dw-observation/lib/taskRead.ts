/**
 * T02 — Canonical Task read gateway.
 *
 * Provides two separately-importable adapters and a selector that
 * resolves both summaries and counts from the SAME selected source,
 * so the page can never mix a real relation with a fixture count.
 *
 * The fixture adapter is dev-only — keep it importable by simulation
 * callers, but the production page must never reach it directly.
 */

import { buildTaskRunIndexV2, resolveFromIndex, type TaskRunRelationRecord } from "@/lib/dwo/taskRunIndex";
import { buildTaskIndex, TASK_META, TASK_RELATION_RECORDS, type TaskMeta } from "@/lib/taskFixtures";
import type { TaskSummary, TaskResolutionStatus } from "./taskTypes";

// ---------------------------------------------------------------------------
// Summary builder
// ---------------------------------------------------------------------------

function buildSummary(
  taskRef: string,
  rel: { status: string; reason: string; relationRevisionId: string | null; rootRunIds: readonly string[] },
  meta: { title: string | null; domain: string | null },
): TaskSummary {
  const rootRunIds = rel.rootRunIds;
  return {
    taskRef,
    title: meta.title,
    domain: meta.domain,
    // null when source did not say — never collapse to 0
    rootRunCount: rootRunIds.length > 0 ? rootRunIds.length : null,
    latestRunId: rootRunIds[0] ?? null,
    latestState: null,
    relationRevision: rel.relationRevisionId
      ? Number.parseInt(rel.relationRevisionId.replace("rel-", ""), 10)
      : null,
    status: rel.status as TaskResolutionStatus,
  };
}

// ---------------------------------------------------------------------------
// Fixture adapter — dev / simulation only
// ---------------------------------------------------------------------------

export function readFixtureSummaries(
  records?: readonly TaskRunRelationRecord[],
): TaskSummary[] {
  const index = buildTaskRunIndexV2(records ?? TASK_RELATION_RECORDS);
  const resolve = (ref: string) => resolveFromIndex(index, ref);
  return TASK_META.map((meta: TaskMeta) => {
    const rel = resolve(meta.taskRef);
    return buildSummary(meta.taskRef, rel, { title: meta.title, domain: meta.domain });
  });
}

// ---------------------------------------------------------------------------
// Real adapter — canonical server read path
// ---------------------------------------------------------------------------

export async function readRealSummaries(
  records: readonly TaskRunRelationRecord[],
): Promise<TaskSummary[]> {
  const index = buildTaskRunIndexV2(records);
  const taskRefs = [...new Set(records.map((r) => r.taskRef))];
  return taskRefs.map((taskRef) => {
    const rel = resolveFromIndex(index, taskRef);
    return buildSummary(taskRef, rel, { title: null, domain: null });
  });
}

// ---------------------------------------------------------------------------
// Selector — resolves both summaries and counts from the SAME source
// ---------------------------------------------------------------------------

function summariesDisagree(a: TaskSummary, b: TaskSummary): boolean {
  return (
    a.status !== b.status ||
    a.rootRunCount !== b.rootRunCount ||
    a.latestRunId !== b.latestRunId ||
    a.relationRevision !== b.relationRevision
  );
}

function unavailable(taskRef: string): TaskSummary {
  return {
    taskRef,
    title: null,
    domain: null,
    rootRunCount: null,
    latestRunId: null,
    latestState: null,
    relationRevision: null,
    status: "UNAVAILABLE",
  };
}

/**
 * Resolve a single task through the gateway.
 *
 * @param taskRef   - task to resolve
 * @param source    - which adapter to prefer ("real" | "fixture")
 * @param realRecords - optional relation records for the real adapter
 * @param fixtureRecords - optional relation records for the fixture adapter
 *
 * Conflict rule: if both sources provide data for the same task at the
 * same revision and they disagree, return CONFLICT regardless of the
 * selected source.  No fallback to the other source when the selected
 * source has no data — the result is UNAVAILABLE.
 */
export async function resolveTask(
  taskRef: string,
  source: "real" | "fixture" = "fixture",
  realRecords?: readonly TaskRunRelationRecord[],
  fixtureRecords?: readonly TaskRunRelationRecord[],
): Promise<TaskSummary> {
  const fixtureSummaries = readFixtureSummaries(fixtureRecords);
  const fixture = fixtureSummaries.find((s) => s.taskRef === taskRef);

  const realSummaries = await readRealSummaries(realRecords ?? []);
  const real = realSummaries.find((s) => s.taskRef === taskRef);

  // Conflict detection: two sources disagree at the same revision
  if (fixture && real && summariesDisagree(fixture, real)) {
    return { ...fixture, status: "CONFLICT" };
  }

  // Return the selected source — no fallback to the other
  if (source === "real") return real ?? unavailable(taskRef);
  return fixture ?? unavailable(taskRef);
}