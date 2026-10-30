import { describe, expect, it, vi } from 'vitest';
import { render, fireEvent, screen, within, act } from '@testing-library/react';
import FixtureLabClient from '@/app/dev/fixtures/FixtureLabClient';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import { projectFixtureReplayView } from '@/lib/dwo/fixtureReplayView';
import type { UnifiedRunWorkspaceModel } from '@/lib/runtime/unifiedRuntime';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
vi.mock('@/components/dwo/RuntimeGraphCanvas', () => ({ default: ({model, selection}: {model: UnifiedRunWorkspaceModel; selection: {id: string}}) => <div data-testid="graph-prefix" data-selected={selection.id}>{model.nodes.map(n => <span key={n.id} data-testid={`state-${n.id}`}>{n.gateState ?? 'UNKNOWN'}</span>)}</div> }));
const catalog = FIXTURE_CATALOG.filter(e => ['DEV-RUN-017','DEV-RUN-022'].includes(e.id));
const models = Object.fromEntries(catalog.map(e => [e.id, materializeFixtureScenario(e)]));
const streams = Object.fromEntries(catalog.map(e => [e.id, models[e.id].nodes.flatMap(n => [...(createFixtureReplaySession(n.id)?.events ?? [])]).sort((a,b) => Number(a.ordinal) - Number(b.ordinal))]));
const mount = () => render(<FixtureLabClient catalog={catalog} models={models} replayEvents={streams} defaultId="DEV-RUN-017" />);
describe('real fixture shared prefix integration', () => {
 it('connects workspace player and selected tree node to the parent session', () => {
  mount();
  fireEvent.click(screen.getByTestId('fixture-catch-up'));
  fireEvent.click(screen.getByTestId('player-first'));
  expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent(`0/${streams['DEV-RUN-017'].length}`);
  expect(screen.getByTestId('workspace-header')).toHaveTextContent('UNKNOWN');
  fireEvent.click(screen.getByTestId('player-next'));
  expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent(`1/${streams['DEV-RUN-017'].length}`);
  fireEvent.click(screen.getByTestId('player-last'));
  fireEvent.click(screen.getByTestId('hierarchy-select-DEV-RUN-019'));
  expect(screen.getByTestId('graph-prefix')).toHaveAttribute('data-selected', 'DEV-RUN-019');
  expect(screen.getByTestId('inspector-node-id')).toHaveTextContent('DEV-RUN-019');
 });
 it('resets arrival bookkeeping when a scenario changes or resets', () => {
  mount();
  fireEvent.click(screen.getByTestId('fixture-catch-up'));
  fireEvent.click(within(screen.getByTestId('fixture-catalog')).getByRole('button', {name: /DEV-RUN-022/}));
  fireEvent.click(screen.getByTestId('fixture-event-arrive'));
  expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent('1/1');
  expect(screen.getByTestId('state-DEV-RUN-022')).toHaveTextContent('WAITING');
  fireEvent.click(screen.getByTestId('fixture-replay-reset'));
  fireEvent.click(screen.getByTestId('fixture-event-arrive'));
  expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent('1/1');
 });
 it('does not expose full-tip state or unbound evidence at the empty prefix', () => {
  const actual = projectFixtureReplayView(models['DEV-RUN-017'], []);
  expect(actual.canonicalHistoryAvailable).toBe(false);
  expect(actual.sourceTerminalMarker).toBeNull();
  expect(actual.nodes.every(n => n.gateId === null && n.gateState === null && n.sourceStatus === 'UNKNOWN' && n.artifacts.length === 0 && n.checkpoints.length === 0)).toBe(true);
 });
 it('plays more than one prefix tick through the parent session and pauses', () => {
  vi.useFakeTimers();
  try {
   mount(); fireEvent.click(screen.getByTestId('fixture-catch-up'));
   fireEvent.click(screen.getByTestId('player-first'));
   fireEvent.click(screen.getByTestId('player-play'));
   act(() => { vi.advanceTimersByTime(750); });
   expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent('1/3');
   act(() => { vi.advanceTimersByTime(750); });
   expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent('2/3');
   fireEvent.click(screen.getByTestId('player-play'));
   act(() => { vi.advanceTimersByTime(1500); });
   expect(screen.getByTestId('fixture-replay-cursor')).toHaveTextContent('2/3');
  } finally { vi.useRealTimers(); }
 });
 it('matches server reducer facts for every prefix of all 29 conforming scenarios', () => {
  const rows = readFileSync(join(process.cwd(), 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line));
  for (const entry of FIXTURE_CATALOG.filter(e => e.kind !== 'NEGATIVE')) {
   const model = materializeFixtureScenario(entry);
   const ids = new Set(model.nodes.map(n => n.id));
   const events = rows.filter(e => ids.has(e.run_id)).sort((a,b) => a.ordinal - b.ordinal);
   for (let cursor = 0; cursor <= events.length; cursor++) {
    const prefix = events.slice(0, cursor);
    const actual = projectFixtureReplayView(model, prefix);
    const expected = materializeFixtureScenario(entry, { events: prefix });
    for (const field of ['status','gate','gateState','sourceTerminalMarker','sourceProfile','syncState','semanticQualification','authorityState','anomalyCount','canonicalHistoryAvailable','projectionStatus'] as const) {
     expect(actual[field], `${entry.id}:${cursor}:${field}`).toEqual(expected[field]);
    }
    const facts = (m: UnifiedRunWorkspaceModel) => m.nodes.map(({id,gateId,gateState,sourceStatus}) => ({id,gateId,gateState,sourceStatus}));
    expect(facts(actual)).toEqual(facts(expected));
   }
  }
 });
 it('preserves the incompatible negative fixture', () => {
  const entry = FIXTURE_CATALOG.find(e => e.id === 'DEV-RUN-020')!;
  const model = materializeFixtureScenario(entry);
  expect(projectFixtureReplayView(model, [])).toEqual(model);
 });
});
