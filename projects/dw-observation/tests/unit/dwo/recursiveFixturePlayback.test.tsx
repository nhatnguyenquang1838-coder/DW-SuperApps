import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PREVIEW_FIXTURE_CATALOG } from '@/lib/dwo/fixturePreviewCatalog';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import spec from '@/dwo-v2/fixtures/DWO-WORK-DEMO-V1/recursive-scenario.json';
import RecursiveFixturePlayback from '@/components/dwo/RecursiveFixturePlayback';
vi.mock('@/components/dwo/UnifiedRunWorkspace', () => ({ default: ({ model }: any) =>
  <div data-testid="projected-workspace">{model.gate}:{model.gateState}:{model.status}:evidence={model.nodes.reduce((n: number, node: any) => n + node.rawEvidence.length, 0)}</div> }));

function mount() {
  const model = materializeFixtureScenario(PREVIEW_FIXTURE_CATALOG.find(r => r.id === spec.rootRunId)!);
  const events = model.nodes.flatMap(node => [...createFixtureReplaySession(node.id)!.events]).sort((a, b) => Number(a.ordinal) - Number(b.ordinal));
  return render(<RecursiveFixturePlayback model={model} events={events} milestones={spec.milestones} initialCursor={1} />);
}
describe('recursive fixture playback is a single prefix-driven workspace', () => {
  it('opens at G0, shows all seven gates, and keeps future evidence out', () => {
    mount();
    expect(screen.getByTestId('projected-workspace').textContent).toBe('G0:ACTIVE:OPEN:evidence=0');
    expect(screen.getByTestId('gate-DEMO-RECURSIVE-ROOT-G0').textContent).toBe('ACTIVE');
    expect(screen.getByTestId('gate-DEMO-RECURSIVE-ROOT-G6').textContent).toBe('NOT OBSERVED');
    expect(screen.getByTestId('recursive-gate-matrix').querySelectorAll('tbody tr')).toHaveLength(4);
  });
  it('moves graph and gate matrix together, with independent parent completion and reversible history', () => {
    mount();
    const digest = screen.getByTestId('recursive-state-digest').textContent;
    fireEvent.click(screen.getByRole('button', { name: 'Atomics complete' }));
    expect(screen.getByTestId('projected-workspace').textContent).toBe('G2:WAITING:OPEN:evidence=0');
    expect(screen.getByTestId('gate-DEMO-RECURSIVE-CHILD-G2').textContent).toBe('WAITING');
    expect(screen.getByTestId('gate-DEMO-RECURSIVE-API-G6').textContent).toBe('PASSED');
    fireEvent.click(screen.getByRole('button', { name: 'Child complete' }));
    expect(screen.getByTestId('projected-workspace').textContent).toBe('G2:WAITING:OPEN:evidence=0');
    expect(screen.getByTestId('gate-DEMO-RECURSIVE-CHILD-G6').textContent).toBe('PASSED');
    fireEvent.click(screen.getByRole('button', { name: 'Root G6 accepted' }));
    expect(screen.getByTestId('projected-workspace').textContent).toContain('G6:PASSED:ACCEPTED:evidence=12');
    expect(screen.getByTestId('recursive-state-digest').textContent).not.toBe(digest);
    fireEvent.click(screen.getByRole('button', { name: 'Start at G0' }));
    expect(screen.getByTestId('projected-workspace').textContent).toBe('G0:ACTIVE:OPEN:evidence=0');
    expect(screen.getByTestId('recursive-state-digest').textContent).toBe(digest);
    expect(screen.getByTestId('recursive-event-history').querySelectorAll('li')).toHaveLength(1);
  });
});
