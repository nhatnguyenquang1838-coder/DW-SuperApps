// Fixture-only operational summary from the same models as run detail.
// A resolved TaskRunIndex relation is membership proof, not completed work.
import type { DashboardProjection } from '@/lib/dashboard/readDashboardProjection';
import { loadPreviewTaskRecords } from './previewTaskRead';
import { buildTaskRunIndexV2, resolveFromIndex } from './taskRunIndex';
import { PREVIEW_FIXTURE_CATALOG } from './fixturePreviewCatalog';
import { materializeFixtureScenario } from './materializeFixtureScenario';
import { createFixtureReplaySession } from './fixtureReplaySession';

export function readPreviewDashboardProjection(): DashboardProjection {
  const records = loadPreviewTaskRecords();
  const index = buildTaskRunIndexV2(records);
  const refs = [...new Set(records.map(record => record.taskRef))];
  const models = new Map(PREVIEW_FIXTURE_CATALOG.map(entry => [entry.id, materializeFixtureScenario(entry)]));
  const projection: DashboardProjection = {
    taskCount: refs.length || null, runCounts: {}, unresolvedCount: 0,
    activeCount: 0, waitingCount: 0, blockedCount: 0, completedCount: 0,
    authorityWaitCount: 0, degradedSourceCount: 0, recentActivity: [], needsAttention: [],
  };
  for (const model of models.values()) {
    const profile = model.sourceProfile ?? 'UNKNOWN';
    projection.runCounts[profile] = (projection.runCounts[profile] ?? 0) + 1;
    if (model.status === 'INCOMPATIBLE') projection.degradedSourceCount!++;
    if (model.authorityState === 'PENDING') projection.authorityWaitCount!++;
    const session = createFixtureReplaySession(model.runId);
    const event = session?.events[session.events.length - 1];
    if (event) projection.recentActivity.push({ runId: model.runId, sourceSystem: profile,
      eventType: typeof event.summary === 'string' ? event.summary : event.gate_state,
      timestamp: event.occurred_at ?? event.created_at ?? null, route: `/runs/${model.runId}` });
  }
  for (const taskRef of refs) {
    const relation = resolveFromIndex(index, taskRef);
    const roots = relation.rootRunIds.map(id => models.get(id));
    if (relation.status !== 'RESOLVED' || roots.length === 0 || roots.some(root => !root)) {
      projection.unresolvedCount!++;
      // Unknown membership is not an execution state. Do not report complete.
      projection.waitingCount!++;
      projection.needsAttention.push({ taskRef, reason: 'RELATION_UNAVAILABLE', route: `/tasks/${taskRef}/runs` });
      continue;
    }
    const present = roots.filter((root): root is NonNullable<typeof root> => !!root);
    const members = present.flatMap(root => [root, ...root.nodes.map(node => models.get(node.id)).filter((m): m is NonNullable<typeof m> => !!m)]);
    if (members.some(model => model.status === 'INCOMPATIBLE' || model.status === 'FAILED' || model.gateState === 'FAILED' || model.gateState === 'BLOCKED' || model.authorityState === 'DENIED')) {
      projection.blockedCount!++;
      projection.needsAttention.push({ taskRef, reason: 'BLOCKED_FAILED_OR_INCOMPATIBLE_RUN', route: `/tasks/${taskRef}/runs` });
    } else if (present.every(root => root.status === 'ACCEPTED') && members.every(model => model.status === 'ACCEPTED')) {
      projection.completedCount!++;
    } else if (members.some(model => model.gateState === 'WAITING' || model.authorityState === 'PENDING')) {
      projection.waitingCount!++;
    } else {
      projection.activeCount!++;
    }
  }
  return projection;
}
