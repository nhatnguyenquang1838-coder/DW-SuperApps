/**
 * T02-F — Fixture Task read adapter (dev / simulation only).
 *
 * Mirrors the real/fixture split in lib/taskRead.ts, but the fixture adapter
 * is self-contained: it loads TaskRunRelationRecords from the materialized
 * DWO-UR-30-V1 pack on disk and resolves them through the same
 * resolveTaskRootRuns / buildTaskRunIndexV2 path the real adapter uses.
 *
 * Production routes must never import this module.
 * No relation is inferred from a run id, branch name, or any string pattern.
 */

import {
  buildTaskRunIndexV2,
  resolveFromIndex,
  type TaskRunRelationRecord,
} from '@/lib/dwo/taskRunIndex';
import type { TaskSummary } from '@/lib/taskTypes';

export const FIXTURE_TASK_RELATIONS_PATH =
  'dwo-v2/fixtures/DWO-UR-30-V1/tasks/task-relations.jsonl';

export interface FixtureTaskReadConfig {
  /** Override the on-disk path (test seam). */
  readonly path?: string;
  /** Override the fs read (test seam). */
  readonly readText?: (path: string) => string;
}

let _fs: typeof import('fs') | null = null;
let _path: typeof import('path') | null = null;

function ensureFs(): typeof import('fs') | null {
  if (_fs !== null) return _fs;
  try {
    _fs = require('fs');
    _path = require('path');
  } catch {
    // Client bundle cannot resolve fs — fixture adapter is server-only.
  }
  return _fs;
}

/**
 * Load fixture TaskRunRelationRecords from the materialized pack.
 *
 * Returns an empty array (never null, never undefined) when the pack is
 * unreadable — the caller must treat that as UNAVAILABLE, not as "no tasks".
 */
export function loadFixtureTaskRecords(config: FixtureTaskReadConfig = {}): readonly TaskRunRelationRecord[] {
  const fs = ensureFs();
  if (!fs) return [];
  const p = _path!;
  const filePath = config.path ?? p.join(process.cwd(), FIXTURE_TASK_RELATIONS_PATH);
  let raw: string;
  try {
    raw = config.readText ? config.readText(filePath) : fs.readFileSync(filePath, 'utf-8');
  } catch {
    return [];
  }
  const records: TaskRunRelationRecord[] = [];
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      records.push(JSON.parse(trimmed) as TaskRunRelationRecord);
    } catch {
      // A malformed line must not poison the whole set; the resolver will
      // report the task as unresolved rather than fabricate a relation.
      continue;
    }
  }
  return records;
}

/** Fixture task metadata (title/domain come from the fixture catalog domains). */
export const FIXTURE_TASK_METAS: readonly {
  readonly taskRef: string;
  readonly title: string | null;
  readonly domain: string | null;
  readonly runCount: number;
}[] = [
  { taskRef: 'TASK-CORE', title: 'Core Universal Runs', domain: 'CORE', runCount: 8 },
  { taskRef: 'TASK-EVENT', title: 'Home Party', domain: 'EVENT', runCount: 1 },
  { taskRef: 'TASK-PARTY', title: 'Party Holding', domain: 'EVENT/PARTY_HOLDING', runCount: 1 },
  { taskRef: 'TASK-RESEARCH', title: 'Research', domain: 'RESEARCH', runCount: 1 },
  { taskRef: 'TASK-WEDDING', title: 'Wedding', domain: 'EVENT/WEDDING', runCount: 1 },
];

function buildSummary(
  taskRef: string,
  rel: { status: string; reason: string; relationRevisionId: string | null; rootRunIds: readonly string[] },
  meta: { title: string | null; domain: string | null },
): TaskSummary {
  return {
    taskRef,
    title: meta.title,
    domain: meta.domain,
    rootRunIds: rel.rootRunIds,
    rootRunCount: rel.rootRunIds.length > 0 ? rel.rootRunIds.length : null,
    latestRunId: rel.rootRunIds[0] ?? null,
    latestState: null,
    relationRevision: rel.relationRevisionId
      ? Number.parseInt(rel.relationRevisionId.replace('rel-', ''), 10)
      : null,
    status: rel.status as TaskSummary['status'],
  };
}

/**
 * Resolve every fixture task through the same index path as the real adapter.
 * Returns summaries in FIXTURE_TASK_METAS order; tasks with no record are
 * UNAVAILABLE (never an empty healthy list).
 */
export function readFixtureTaskSummaries(
  config: FixtureTaskReadConfig = {},
): TaskSummary[] {
  const records = loadFixtureTaskRecords(config);
  const index = buildTaskRunIndexV2(records);
  return FIXTURE_TASK_METAS.map((meta) => {
    const rel = resolveFromIndex(index, meta.taskRef);
    return buildSummary(meta.taskRef, rel, { title: meta.title, domain: meta.domain });
  });
}

/**
 * Resolve a single fixture task. Returns UNAVAILABLE when the fixture pack
 * has no relation record for it — never falls back to the real adapter.
 */
export function resolveFixtureTask(
  taskRef: string,
  config: FixtureTaskReadConfig = {},
): TaskSummary {
  const records = loadFixtureTaskRecords(config);
  const index = buildTaskRunIndexV2(records);
  const rel = resolveFromIndex(index, taskRef);
  const meta = FIXTURE_TASK_METAS.find((m) => m.taskRef === taskRef) ?? {
    taskRef,
    title: null,
    domain: null,
    runCount: 0,
  };
  return buildSummary(taskRef, rel, { title: meta.title, domain: meta.domain });
}

/** Fixture adapter grants read-only access; no effect capability. */
export const FIXTURE_TASK_CAPABILITIES = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);

/** Convenience: list every fixture task relation as TaskSummary[]. */
export async function listFixtureTaskRelations(
  config: FixtureTaskReadConfig = {},
): Promise<TaskSummary[]> {
  return readFixtureTaskSummaries(config);
}

/** Convenience: resolve a single fixture task relation. Returns UNAVAILABLE when absent. */
export async function getFixtureTaskRelation(
  taskRef: string,
  config: FixtureTaskReadConfig = {},
): Promise<TaskSummary | null> {
  const records = loadFixtureTaskRecords(config);
  const index = buildTaskRunIndexV2(records);
  const rel = resolveFromIndex(index, taskRef);
  if (rel.status !== 'RESOLVED' || rel.rootRunIds.length === 0) return null;
  const meta = FIXTURE_TASK_METAS.find((m) => m.taskRef === taskRef) ?? {
    taskRef,
    title: null,
    domain: null,
    runCount: 0,
  };
  return buildSummary(taskRef, rel, { title: meta.title, domain: meta.domain });
}