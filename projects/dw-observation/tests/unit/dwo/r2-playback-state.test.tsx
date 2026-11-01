import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import UnifiedRunWorkspace from '@/components/dwo/UnifiedRunWorkspace';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';

const fixture = FIXTURE_CATALOG.find((row) => row.id === 'DEV-RUN-024')!;
const model = materializeFixtureScenario(fixture);
afterEach(cleanup);

describe('R2 current view and playback state', () => {
  it('selects the available tip and remains paused when Current is chosen', () => {
    render(<UnifiedRunWorkspace model={model} />);
    fireEvent.click(screen.getAllByTestId('player-live-sim').at(-1)!);
    expect(screen.getByTestId('player-scrubber')).toHaveValue('2');
    expect(screen.getByTestId('player-play')).toHaveAccessibleName('Play replay');
  });

  it('preserves controlled Fixture Lab mode and cursor callbacks', () => {
    const onCursor = vi.fn();
    const onMode = vi.fn();
    render(<UnifiedRunWorkspace model={model} replayCursor={1} replayTotal={3} replayMode="REPLAY" onReplayCursorChange={onCursor} onReplayModeChange={onMode} />);
    fireEvent.click(screen.getAllByTestId('player-live-sim').at(-1)!);
    expect(onMode).toHaveBeenCalledWith('LIVE');
    expect(onCursor).not.toHaveBeenCalled();
    expect(screen.getByTestId('player-scrubber')).toHaveValue('1');
  });
});
