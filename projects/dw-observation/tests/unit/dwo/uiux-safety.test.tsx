import { readFileSync } from 'node:fs';
import path from 'node:path';
import { render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import WorkspaceHeader from '@/components/dwo/WorkspaceHeader';
import RuntimePlayer from '@/components/dwo/RuntimePlayer';
import type { UnifiedRunWorkspaceModel } from '@/lib/runtime/unifiedRuntime';

const fixture: UnifiedRunWorkspaceModel = {
  runId: 'DEV-UX', taskRef: null, mode: 'SIMULATED', status: 'OPEN', hierarchy: null,
  nodes: [], edges: [], orderedSteps: [], currentSequence: null, canonicalHistoryAvailable: false,
  projectionStatus: 'UNKNOWN', sourceDigest: null,
};

describe('UX repair safety and accessibility', () => {
  it('uses defined design tokens rather than silently inheriting an absent guidance color', () => {
    const globals = readFileSync(path.resolve(process.cwd(), 'app/globals.css'), 'utf8');
    const declared = new Set([...globals.matchAll(/(--dwo-[\w-]+)\s*:/g)].map(match => match[1]));
    for (const file of ['RunStatusAxes.module.css', 'WorkspaceHeader.module.css', 'NextFlowPanel.module.css']) {
      const css = readFileSync(path.resolve(process.cwd(), 'components/dwo', file), 'utf8');
      for (const match of css.matchAll(/var\((--dwo-[\w-]+)\)/g)) {
        expect(declared.has(match[1]), `${file}: undefined ${match[1]}`).toBe(true);
      }
    }
  });

  it('never calls the fixture LIVE cursor mode a production source', () => {
    render(<WorkspaceHeader model={fixture} mode="LIVE" onModeChange={() => {}} />);
    expect(screen.getByTestId('workspace-mode-explanation')).toHaveTextContent(/fixture/i);
    expect(screen.getByTestId('workspace-header').querySelector('.dwo-ws-badge')).toHaveTextContent('Current fixture state');
    expect(within(screen.getByRole('combobox', { name: 'Workspace mode' })).getByRole('option', { name: 'Current fixture state' })).toHaveValue('LIVE');
  });

  it('names player controls and keeps fixture-current copy distinct from a live source', () => {
    const noop = () => {};
    render(<RuntimePlayer cursor={0} len={3} mode="SIMULATED" speed={750} playing={false} label="DEV-UX"
      fixturePreview onFirst={noop} onPrev={noop} onToggle={noop} onNext={noop} onLast={noop}
      onScrub={noop} onMode={noop} onSpeed={noop} />);
    expect(screen.getByTestId('player-live-sim')).toHaveTextContent('Current fixture state');
    expect(screen.getByRole('button', { name: 'First step' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Previous step' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Play replay' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Next step' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Last step' })).toBeVisible();
    expect(screen.getByRole('slider', { name: 'Replay position' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'Playback mode' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'Playback speed' })).toBeVisible();
  });
});
