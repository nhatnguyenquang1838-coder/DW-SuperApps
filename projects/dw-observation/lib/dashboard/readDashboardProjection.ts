/**
 * T08 — Operational Dashboard with source-backed aggregates.
 *
 * TECH_SPEC §4 (/dashboard) and §10 (dashboard aggregation contract).
 *
 * HARD RULE: an unavailable source renders as explicit null, never as 0.
 * No decorative fake metrics. No fixture-only counts in real mode.
 * Zero and unavailable are different facts.
 *
 * Uses the dwo: Tailwind aliases and reuses authorityVocabulary + liveState
 * vocabulary — the live projection state machine is the single source of
 * truth for lifecycle states.
 */

import { buildTaskRunIndexV2, resolveFromIndex, type TaskRunRelationRecord } from "@/lib/dwo/taskRunIndex";
import { listRuns } from "@/lib/observatory";
import type { RunView } from "@/lib/observatory";

// ---------------------------------------------------------------------------
// DashboardProjection — TECH_SPEC §10 verbatim
// ---------------------------------------------------------------------------

export interface DashboardProjection {
  taskCount: number | null;
  runCounts: Record<string, number | null>;
  unresolvedCount: number | null;
  authorityWaitCount: number | null;
  degradedSourceCount: number | null;
  recentActivity: unknown[];
  needsAttention: unknown[];
  // Four-bucket population model — TECH_SPEC §10
  activeCount: number | null;
  waitingCount: number | null;
  blockedCount: number | null;
  completedCount: number | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type DataSource = "real" | "fixture";

/** Group runs by sourceSystem, counting per-source totals. */
function computeRunCounts(runs: RunView[]): Record<string, number | null> {
  const grouped: Record<string, number> = {};
  for (const run of runs) {
    const src = run.sourceSystem || "unknown";
    grouped[src] = (grouped[src] || 0) + 1;
  }
  return grouped;
}

/** Extract the most recent events across runs as activity entries. */
function computeRecentActivity(runs: RunView[]): unknown[] {
  const activity: unknown[] = [];
  for (const run of runs) {
    const lastEvent = run.events[run.events.length - 1];
    if (!lastEvent) continue;
    activity.push({
      runId: run.runId,
      sourceSystem: run.sourceSystem,
      eventType: lastEvent.eventType,
      timestamp: lastEvent.occurredAt,
      route: `/runs/${run.runId}`,
    });
  }
  return activity;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Produce a source-backed dashboard projection.
 *
 * @param dataSource  - "real" (production) or "fixture" (dev/simulation)
 * @param records     - optional relation records for the task source.
 *                      When absent or empty, the task source is unavailable
 *                      and task-scoped aggregates render as null (never 0).
 */
export function readDashboardProjection(
  dataSource: DataSource = "real",
  records?: readonly TaskRunRelationRecord[]
): DashboardProjection {
  const hasTaskRecords = records !== undefined && records.length > 0;

  // --- Task aggregates (source: task relation records) ---
  let taskCount: number | null = null;
  let unresolvedCount: number | null = null;
  let activeCount: number | null = null;
  let waitingCount: number | null = null;
  let blockedCount: number | null = null;
  let completedCount: number | null = null;
  const needsAttention: unknown[] = [];

  if (hasTaskRecords) {
    const index = buildTaskRunIndexV2(records);
    const taskRefs = [...new Set(records.map((r) => r.taskRef))];
    let resolved = 0;
    let unresolved = 0;
    let active = 0;
    let waiting = 0;
    let blocked = 0;

    for (const ref of taskRefs) {
      const rel = resolveFromIndex(index, ref);
      if (rel.status === "RESOLVED") {
        resolved++;
      } else {
        unresolved++;
        // Classify UNKNOWN_UNRESOLVED into active / waiting / blocked
        const terminalReasons = [
          "RELATION_CONFLICT",
          "SUPERSESSION_CYCLE",
          "SUPERSEDED_REVISION",
          "MISSING_TASK_REF",
          "MISSING_RELATION_REVISION",
          "MISSING_SOURCE_IDENTITY",
          "MISSING_SOURCE_DIGEST",
          "MISSING_ROOT_RUN_ID",
          "NEGATIVE_DURABLE_POSITION",
        ];
        const taskRecord = records.find((r) => r.taskRef === ref);
        const hasRuns = taskRecord && taskRecord.rootRunIds.length > 0;
        if (terminalReasons.includes(rel.reason)) {
          blocked++;
        } else if (hasRuns) {
          active++;
        } else {
          waiting++;
        }
        needsAttention.push({
          type: "task",
          taskRef: ref,
          status: rel.status,
          reason: rel.reason,
          route: `/tasks/${ref}`,
        });
      }
    }

    taskCount = resolved + unresolved;
    unresolvedCount = unresolved;
    activeCount = active;
    waitingCount = waiting;
    blockedCount = blocked;
    completedCount = resolved;
  }

  // --- Run aggregates (source: observatory listRuns) ---
  // `DataSource` here is the DWO vocabulary ("real" | "fixture"); observatory's
  // `DataSource` is "real" | "mock". They are the same two modes under different
  // names — map explicitly rather than importing and leaking the older spelling
  // into the dashboard API. T08 originally declared a local `DataSource` union
  // with a "fixture" member and passed it straight to listRuns(), which typecheck
  // rejected: the type existed, it just was not this type.
  const runs = listRuns(dataSource === "fixture" ? "mock" : dataSource);
  const runCounts = computeRunCounts(runs);
  const recentActivity = computeRecentActivity(runs);

  // --- Authority waits (source: authority evidence) ---
  // No authority evidence passed in → null (unavailable, never 0).
  let authorityWaitCount: number | null = null;

  // --- Degraded / unavailable sources (source: live state) ---
  // No live-state bootstrap passed in → null (unavailable, never 0).
  let degradedSourceCount: number | null = null;

  return {
    taskCount,
    runCounts,
    unresolvedCount,
    authorityWaitCount,
    degradedSourceCount,
    recentActivity,
    needsAttention,
    activeCount,
    waitingCount,
    blockedCount,
    completedCount,
  };
}