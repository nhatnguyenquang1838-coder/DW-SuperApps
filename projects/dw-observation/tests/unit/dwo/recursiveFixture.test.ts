import { describe, expect, it } from 'vitest';
import { PREVIEW_FIXTURE_CATALOG } from '@/lib/dwo/fixturePreviewCatalog';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import { projectFixtureReplayView } from '@/lib/dwo/fixtureReplayView';
import type { ProjectionEvent } from '@/lib/live';

const rootId = 'DEMO-RECURSIVE-ROOT';
const childId = 'DEMO-RECURSIVE-CHILD';
const atoms = ['DEMO-RECURSIVE-API', 'DEMO-RECURSIVE-UI'];
function scenario() {
  const root = PREVIEW_FIXTURE_CATALOG.find(run => run.id === rootId);
  expect(root, 'recursive scenario must be explicitly registered').toBeDefined();
  const model = materializeFixtureScenario(root!);
  const events = model.nodes.flatMap(node => [...createFixtureReplaySession(node.id)!.events])
    .sort((a, b) => Number(a.ordinal) - Number(b.ordinal));
  return { model, events };
}

describe('recursive G0–G6 work fixture', () => {
  it('has explicit ROOT -> CHILD -> ATOMIC topology and full histories for every run', () => {
    const { model } = scenario();
    expect(model.nodes).toHaveLength(4);
    expect(model.nodes.every(node => JSON.stringify(node.declaredGates) === JSON.stringify(['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6']))).toBe(true);
    expect(model.hierarchy).toMatchObject({ id: rootId, atomic: false, children: [
      { id: childId, parent: rootId, atomic: false, children: atoms.map(id => ({ id, parent: childId, atomic: true, children: [] })) },
    ] });
    expect(PREVIEW_FIXTURE_CATALOG.find(r => r.id === childId)?.kind).toBe('CHILD');
    for (const id of [rootId, childId, ...atoms]) {
      const session = createFixtureReplaySession(id)!;
      expect([...new Set(session.events.map(event => event.gate))]).toEqual(['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6']);
      expect(session.frame.anomalies).toEqual([]);
      expect(session.events.at(-1)?.run_state).toBe('ACCEPTED');
    }
  });
  it('keeps parent at G2 WAITING after descendants finish, until its own transition', () => {
    const { model, events } = scenario();
    const acceptedPosition = (id: string) => events.findIndex(e => e.run_id === id && e.run_state === 'ACCEPTED') + 1;
    const atomicDone = Math.max(...atoms.map(acceptedPosition));
    const prefix = projectFixtureReplayView(model, events.slice(0, atomicDone));
    expect(prefix.gate).toBe('G2');
    expect(prefix.gateState).toBe('WAITING');
    expect(prefix.status).toBe('OPEN');
    expect(prefix.nodes.find(n => n.id === childId)?.gateState).toBe('WAITING');
    expect(prefix.nodes.filter(n => atoms.includes(n.id)).every(n => n.gateId === 'G6' && n.gateState === 'PASSED')).toBe(true);
    const childDone = projectFixtureReplayView(model, events.slice(0, acceptedPosition(childId)));
    expect(childDone.nodes.find(n => n.id === childId)?.gateState).toBe('PASSED');
    expect(childDone.gateState).toBe('WAITING');
    expect(childDone.status).toBe('OPEN');
    expect(projectFixtureReplayView(model, events).status).toBe('ACCEPTED');
  });
  it('starts at G0 and evolves node state from the selected prefix without future evidence', () => {
    const { model, events } = scenario();
    const first = projectFixtureReplayView(model, events.slice(0, 1));
    expect(first.gate).toBe('G0');
    expect(first.gateState).toBe('ACTIVE');
    expect(first.nodes.find(n => n.id === rootId)?.gateId).toBe('G0');
    expect(first.nodes.find(n => n.id === childId)?.gateId).toBeNull();
    expect(first.nodes.every(n => n.rawEvidence?.length === 0 && n.artifacts.length === 0)).toBe(true);
    expect(events.every((e: ProjectionEvent) => e.synthetic === true)).toBe(true);
    expect(new Set(events.map(e => e.event_id)).size).toBe(events.length);
  });
});
