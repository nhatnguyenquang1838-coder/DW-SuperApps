import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import UnifiedRunWorkspace from '@/components/dwo/UnifiedRunWorkspace';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';

const model = materializeFixtureScenario(FIXTURE_CATALOG.find((row) => row.id === 'DEV-RUN-024')!);
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('R3-01 active playback speed', () => {
  it('reschedules a running uncontrolled player when speed changes', () => {
    vi.useFakeTimers();
    render(<UnifiedRunWorkspace model={model} />);
    fireEvent.change(screen.getByTestId('player-speed'), { target: { value: '1200' } });
    fireEvent.click(screen.getByTestId('player-play'));
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.change(screen.getByTestId('player-speed'), { target: { value: '400' } });
    act(() => { vi.advanceTimersByTime(400); });
    expect(screen.getByTestId('player-scrubber')).toHaveValue('1');
    expect(screen.getByTestId('player-play')).toHaveAccessibleName('Pause replay');
    act(() => { vi.advanceTimersByTime(400); });
    expect(screen.getByTestId('player-scrubber')).toHaveValue('2');
    act(() => { vi.advanceTimersByTime(400); });
    expect(screen.getByTestId('player-play')).toHaveAccessibleName('Play replay');
  });

  it('uses the selected speed for controlled prefix cursors', () => {
    vi.useFakeTimers();
    const onCursor = vi.fn();
    render(<UnifiedRunWorkspace model={model} replayCursor={0} replayTotal={3} replayMode="REPLAY" onReplayCursorChange={onCursor} />);
    fireEvent.change(screen.getByTestId('player-speed'), { target: { value: '1200' } });
    fireEvent.click(screen.getByTestId('player-play'));
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.change(screen.getByTestId('player-speed'), { target: { value: '400' } });
    act(() => { vi.advanceTimersByTime(400); });
    expect(onCursor).toHaveBeenLastCalledWith(1);
  });
});
