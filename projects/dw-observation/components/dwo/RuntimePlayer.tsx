"use client";

import type { WorkspaceMode } from "@/lib/runtime/unifiedRuntime";

/**
 * RuntimePlayer — adapted for WorkspaceMode (LIVE / REPLAY / SIMULATED).
 * Preserves follow-cursor and layout controls from login-epic.
 */
export default function RuntimePlayer({
  cursor,
  len,
  mode,
  speed,
  playing,
  label,
  onFirst,
  onPrev,
  onToggle,
  onNext,
  onLast,
  onScrub,
  onMode,
  onSpeed,
}: {
  cursor: number;
  len: number;
  mode: WorkspaceMode;
  speed: number;
  playing: boolean;
  label: string;
  onFirst: () => void;
  onPrev: () => void;
  onToggle: () => void;
  onNext: () => void;
  onLast: () => void;
  onScrub: (c: number) => void;
  onMode: (m: WorkspaceMode) => void;
  onSpeed: (ms: number) => void;
}) {
  return (
    <div className="dwo-player" data-testid="runtime-player">
      <div className="dwo-player-controls">
        <button className="dwo-player-btn" data-testid="player-first" onClick={onFirst}>⏮</button>
        <button className="dwo-player-btn" data-testid="player-prev" onClick={onPrev}>◀</button>
        <button className="dwo-player-btn dwo-player-primary" data-testid="player-play" onClick={onToggle}>
          {playing ? "❚❚" : "▶"}
        </button>
        <button className="dwo-player-btn" data-testid="player-next" onClick={onNext}>▶|</button>
        <button className="dwo-player-btn" data-testid="player-last" onClick={onLast}>⏭</button>
        <button
          className="dwo-player-btn dwo-player-live"
          data-testid="player-live-sim"
          onClick={() => onMode("LIVE")}
        >
          ● LIVE
        </button>
      </div>
      <div className="dwo-player-scrub">
        <div className="dwo-player-scrub-info">
          <span>{label}</span>
          <span>
            {cursor + 1} / {len}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, len - 1)}
          value={cursor}
          data-testid="player-scrubber"
          onChange={(e) => onScrub(Number(e.target.value))}
        />
      </div>
      <div className="dwo-player-selects">
        <select
          value={mode}
          onChange={(e) => onMode(e.target.value as WorkspaceMode)}
          data-testid="player-mode"
        >
          <option value="LIVE">LIVE</option>
          <option value="REPLAY">REPLAY</option>
          <option value="SIMULATED">SIMULATED</option>
        </select>
        <select
          value={speed}
          data-testid="player-speed"
          onChange={(e) => onSpeed(Number(e.target.value))}
        >
          <option value={1200}>0.5x</option>
          <option value={750}>1x</option>
          <option value={400}>2x</option>
        </select>
      </div>
    </div>
  );
}