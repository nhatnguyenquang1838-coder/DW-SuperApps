import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RuntimePlayer from '@/components/dwo/RuntimePlayer';
import UnifiedRunWorkspace from '@/components/dwo/UnifiedRunWorkspace';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';

afterEach(() => { cleanup(); vi.useRealTimers(); });
const callbacks = () => ({ onFirst: vi.fn(), onPrev: vi.fn(), onToggle: vi.fn(), onNext: vi.fn(), onLast: vi.fn(), onScrub: vi.fn(), onMode: vi.fn(), onSpeed: vi.fn() });
const model = materializeFixtureScenario(FIXTURE_CATALOG.find((row) => row.id === 'DEV-RUN-024')!);

function renderPlayer(cursorIsPrefix = false) {
  const cb = callbacks();
  render(<RuntimePlayer cursor={0} cursorIsPrefix={cursorIsPrefix} len={0} mode="REPLAY" speed={750} playing={false} label="Empty" {...cb} />);
  return cb;
}

describe('R3-02 zero-step runtime player', () => {
  it.each([false, true])('reports 0 / 0 and denies all actions when empty (prefix cursor: %s)', (cursorIsPrefix) => {
    const cb = renderPlayer(cursorIsPrefix);
    expect(screen.getByText('0 / 0')).toBeInTheDocument();
    expect(screen.getByText(/No replay steps are available/i)).toBeInTheDocument();
    for (const id of ['player-first', 'player-prev', 'player-play', 'player-next', 'player-last', 'player-live-sim', 'player-scrubber', 'player-mode', 'player-speed']) expect(screen.getByTestId(id)).toBeDisabled();
    fireEvent.click(screen.getByTestId('player-first'));
    fireEvent.click(screen.getByTestId('player-prev'));
    fireEvent.click(screen.getByTestId('player-play'));
    fireEvent.click(screen.getByTestId('player-next'));
    fireEvent.click(screen.getByTestId('player-last'));
    fireEvent.click(screen.getByTestId('player-live-sim'));
    fireEvent.change(screen.getByTestId('player-scrubber'), { target: { value: '0' } });
    fireEvent.change(screen.getByTestId('player-mode'), { target: { value: 'LIVE' } });
    fireEvent.change(screen.getByTestId('player-speed'), { target: { value: '400' } });
    expect(cb.onFirst).not.toHaveBeenCalled();
    expect(cb.onPrev).not.toHaveBeenCalled();
    expect(cb.onToggle).not.toHaveBeenCalled();
    expect(cb.onNext).not.toHaveBeenCalled();
    expect(cb.onLast).not.toHaveBeenCalled();
    expect(cb.onScrub).not.toHaveBeenCalled();
    expect(cb.onMode).not.toHaveBeenCalled();
    expect(cb.onSpeed).not.toHaveBeenCalled();
  });

  it('keeps populated playback controls enabled and dispatches callbacks', () => {
    const cb = callbacks();
    render(<RuntimePlayer cursor={1} len={3} mode="REPLAY" speed={750} playing={false} label="Populated" {...cb} />);
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    for (const id of ['player-first', 'player-prev', 'player-play', 'player-next', 'player-last', 'player-live-sim', 'player-scrubber', 'player-mode', 'player-speed']) expect(screen.getByTestId(id)).toBeEnabled();
    fireEvent.click(screen.getByTestId('player-first'));
    fireEvent.click(screen.getByTestId('player-prev'));
    fireEvent.click(screen.getByTestId('player-play'));
    fireEvent.click(screen.getByTestId('player-next'));
    fireEvent.click(screen.getByTestId('player-last'));
    fireEvent.click(screen.getByTestId('player-live-sim'));
    fireEvent.change(screen.getByTestId('player-scrubber'), { target: { value: '2' } });
    fireEvent.change(screen.getByTestId('player-mode'), { target: { value: 'LIVE' } });
    fireEvent.change(screen.getByTestId('player-speed'), { target: { value: '400' } });
    expect(cb.onFirst).toHaveBeenCalledOnce();
    expect(cb.onPrev).toHaveBeenCalledOnce();
    expect(cb.onToggle).toHaveBeenCalledOnce();
    expect(cb.onNext).toHaveBeenCalledOnce();
    expect(cb.onLast).toHaveBeenCalledOnce();
    expect(cb.onScrub).toHaveBeenCalledWith(2);
    expect(cb.onMode).toHaveBeenCalledWith('LIVE');
    expect(cb.onSpeed).toHaveBeenCalledWith(400);
  });

  it('stops active controlled playback immediately when the available steps become empty', () => {
    vi.useFakeTimers();
    const onCursor = vi.fn();
    const view = render(<UnifiedRunWorkspace model={model} replayCursor={0} replayTotal={3} replayMode="REPLAY" onReplayCursorChange={onCursor} />);
    fireEvent.click(screen.getByTestId('player-play'));
    expect(screen.getByTestId('player-play')).toHaveAccessibleName('Pause replay');
    view.rerender(<UnifiedRunWorkspace model={model} replayCursor={0} replayTotal={0} replayMode="REPLAY" onReplayCursorChange={onCursor} />);
    expect(screen.getByText('0 / 0')).toBeInTheDocument();
    expect(screen.getByTestId('player-play')).toBeDisabled();
    expect(screen.getByTestId('player-play')).toHaveAccessibleName('Play replay');
    act(() => { vi.advanceTimersByTime(2000); });
    expect(onCursor).not.toHaveBeenCalled();
  });
});
