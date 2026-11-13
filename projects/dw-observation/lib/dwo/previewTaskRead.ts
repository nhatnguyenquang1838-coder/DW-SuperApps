// Preview-only composition of two explicit fixture packs. Never used by Real.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadFixtureTaskRecords, listFixtureTaskRelations, getFixtureTaskRelation } from './fixtureTaskRead';
import { buildTaskRunIndexV2, resolveFromIndex, type TaskRunRelationRecord } from './taskRunIndex';
import type { TaskSummary } from '@/lib/taskTypes';
import metadata from '@/dwo-v2/fixtures/DWO-WORK-DEMO-V1/tasks/metadata.json';
import { WORK_DEMO_PACK } from './fixturePreviewCatalog';

function loadDemoRecords(): TaskRunRelationRecord[] {
  try {
    return readFileSync(join(process.cwd(), 'dwo-v2', 'fixtures', WORK_DEMO_PACK, 'tasks', 'task-relations.jsonl'), 'utf8')
      .split('\n').filter(line => line.trim()).map(line => JSON.parse(line) as TaskRunRelationRecord);
  } catch { return []; }
}
export function loadPreviewTaskRecords(): readonly TaskRunRelationRecord[] {
  return [...loadFixtureTaskRecords(), ...loadDemoRecords()];
}
function demoSummaries(): TaskSummary[] {
  const index = buildTaskRunIndexV2(loadDemoRecords());
  return metadata.map(meta => {
    const rel = resolveFromIndex(index, meta.taskRef);
    return { taskRef: meta.taskRef, title: meta.title, domain: meta.domain,
      rootRunIds: rel.rootRunIds, rootRunCount: rel.status === 'RESOLVED' ? rel.rootRunIds.length : null,
      latestRunId: rel.rootRunIds[0] ?? null, latestState: null,
      relationRevision: rel.relationRevisionId === 'rel-1' ? 1 : null, status: rel.status };
  });
}
export async function listPreviewTaskRelations(): Promise<TaskSummary[]> {
  return [...await listFixtureTaskRelations(), ...demoSummaries()];
}
export async function getPreviewTaskRelation(taskRef: string): Promise<TaskSummary | null> {
  const demo = demoSummaries().find(row => row.taskRef === taskRef);
  return demo ? (demo.status === 'RESOLVED' ? demo : null) : getFixtureTaskRelation(taskRef);
}
