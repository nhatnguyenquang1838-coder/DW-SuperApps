import { describe, it, expect } from 'vitest';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import { PREVIEW_FIXTURE_CATALOG, fixturePackForRun } from '@/lib/dwo/fixturePreviewCatalog';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import { loadPreviewTaskRecords, listPreviewTaskRelations } from '@/lib/dwo/previewTaskRead';
import { readFixtureEvidence } from '@/lib/dwo/fixtureEvidenceRead';
import { projectFixtureReplayView } from '@/lib/dwo/fixtureReplayView';
import { readPreviewDashboardProjection } from '@/lib/dwo/previewDashboard';

const roots = ['DEMO-DELIVERY-ROOT', 'DEMO-BLOCKED-ROOT', 'DEMO-RETRY-ROOT'];
const env = { NODE_ENV: 'development', OBSERVATORY_DATA_SOURCE: 'fixture' };

describe('additive synthetic work-demo fixture pack', () => {
  it('retains the sealed 30 and adds thirteen distinct demo runs, never guessed 031+ ids', () => {
    expect(FIXTURE_CATALOG).toHaveLength(30);
    expect(PREVIEW_FIXTURE_CATALOG).toHaveLength(43);
    expect(new Set(PREVIEW_FIXTURE_CATALOG.map(r => r.id)).size).toBe(43);
    expect(fixturePackForRun('DEV-RUN-031')).toBeNull();
  });
  it('resolves four explicit demo task relations alongside the five canonical tasks', async () => {
    expect(loadPreviewTaskRecords()).toHaveLength(9);
    const tasks = await listPreviewTaskRelations();
    expect(tasks).toHaveLength(9);
    for (const root of roots) expect(tasks.some(t => t.status === 'RESOLVED' && t.rootRunIds.includes(root))).toBe(true);
  });
  it.each(roots)('%s has genuine multi-event fixture history, child graph and raw evidence', runId => {
    const entry = PREVIEW_FIXTURE_CATALOG.find(r => r.id === runId)!;
    const model = materializeFixtureScenario(entry);
    const session = createFixtureReplaySession(runId)!;
    expect(model.mode).toBe('SIMULATED');
    expect(model.taskRef).toMatch(/^DEMO-TASK-/);
    expect(model.nodes).toHaveLength(3);
    expect(model.edges.some(e => e.kind === 'DEPENDENCY')).toBe(true);
    expect(model.nodes.every(n => n.rawEvidence!.length > 0)).toBe(true);
    expect(session.total).toBeGreaterThan(6);
    expect(session.frame.anomalies).toEqual([]);
    expect(session.events.every(e => e.synthetic === true && typeof e.source_event_id === 'string')).toBe(true);
    const start = projectFixtureReplayView(model, []);
    expect(start.nodes.every(n => n.rawEvidence!.length === 0)).toBe(true);
    const first = session.enterReplay(1);
    const tip = first.resumeLive();
    expect(first.frame.stateDigest).not.toBe(tip.frame.stateDigest);
    expect(tip.cursor).toBe(tip.total);
  });
  it('keeps accepted, blocked/denied and retry histories materially different', () => {
    const models = roots.map(id => materializeFixtureScenario(PREVIEW_FIXTURE_CATALOG.find(r => r.id === id)!));
    expect(models[0].status).toBe('ACCEPTED');
    expect(models[1].gateState).toBe('BLOCKED');
    expect(models[1].authorityState).toBe('DENIED');
    expect(models[2].status).toBe('OPEN');
    const retry = createFixtureReplaySession(roots[2])!;
    expect(retry.events.some(e => e.event_type === 'gate_failed')).toBe(true);
    expect(retry.events.some(e => e.summary === 'Retry execution after verification failure')).toBe(true);
  });
  it('dashboard counts work states, not resolved relations as completed work', () => {
    const projection = readPreviewDashboardProjection();
    expect(projection.taskCount).toBe(9);
    expect(projection.completedCount).toBe(2);
    expect(projection.activeCount).toBeGreaterThan(0);
    expect(projection.blockedCount).toBeGreaterThan(0);
    expect(projection.waitingCount).toBeGreaterThan(0);
    expect(projection.activeCount! + projection.waitingCount! + projection.blockedCount! + projection.completedCount!).toBe(9);
    expect(Object.values(projection.runCounts).reduce<number>((sum, n) => sum + (n ?? 0), 0)).toBe(43);
  });
  it('serves bound demo evidence only in non-production Fixture; rejects cross-run and traversal', () => {
    const id = roots[0];
    const ref = `execution/${id}-execution.json`;
    const result = readFixtureEvidence(id, ref, env);
    expect(result.ok).toBe(true);
    if (result.ok) expect(JSON.parse(result.text).synthetic).toBe(true);
    expect(readFixtureEvidence(id, ref, { ...env, NODE_ENV: 'production' }).ok).toBe(false);
    expect(readFixtureEvidence(id, ref, { ...env, OBSERVATORY_DATA_SOURCE: 'real' }).ok).toBe(false);
    expect(readFixtureEvidence(roots[1], ref, env).ok).toBe(false);
    expect(readFixtureEvidence(id, '../catalog.json', env).ok).toBe(false);
  });
});
