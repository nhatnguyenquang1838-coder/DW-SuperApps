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
  cursorIsPrefix = false,
  fixturePreview = false,
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
  cursorIsPrefix?: boolean;
  fixturePreview?: boolean;
}) {
  const hasSteps = len > 0;
  const position = hasSteps ? (cursorIsPrefix ? cursor : cursor + 1) : 0;
  return (
    <div className="dwo-player" data-testid="runtime-player">
      <div className="dwo-player-controls">
        <button className="dwo-player-btn" data-testid="player-first" aria-label="First step" disabled={!hasSteps} onClick={() => { if (hasSteps) onFirst(); }}>⏮</button>
        <button className="dwo-player-btn" data-testid="player-prev" aria-label="Previous step" disabled={!hasSteps} onClick={() => { if (hasSteps) onPrev(); }}>◀</button>
        <button className="dwo-player-btn dwo-player-primary" data-testid="player-play" aria-label={playing ? "Pause replay" : "Play replay"} disabled={!hasSteps} onClick={() => { if (hasSteps) onToggle(); }}>
          {playing ? "❚❚" : "▶"}
        </button>
        <button className="dwo-player-btn" data-testid="player-next" aria-label="Next step" disabled={!hasSteps} onClick={() => { if (hasSteps) onNext(); }}>▶|</button>
        <button className="dwo-player-btn" data-testid="player-last" aria-label="Last step" disabled={!hasSteps} onClick={() => { if (hasSteps) onLast(); }}>⏭</button>
        <button
          className="dwo-player-btn dwo-player-live"
          data-testid="player-live-sim"
          disabled={!hasSteps}
          onClick={() => { if (hasSteps) onMode("LIVE"); }}
        >
          {fixturePreview ? "Current fixture state" : "● LIVE"}
        </button>
      </div>
      {!hasSteps && <p className="dwo-player-empty" role="status">No replay steps are available.</p>}
      <div className="dwo-player-scrub">
        <div className="dwo-player-scrub-info">
          <span>{label}</span>
          <span>
            {position} / {len}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, cursorIsPrefix ? len : len - 1)}
          value={cursor}
          data-testid="player-scrubber"
          aria-label="Replay position"
          disabled={!hasSteps}
          onChange={(e) => { if (hasSteps) onScrub(Number(e.target.value)); }}
        />
      </div>
      <div className="dwo-player-selects">
        <select
          value={mode}
          onChange={(e) => { if (hasSteps) onMode(e.target.value as WorkspaceMode); }}
          data-testid="player-mode"
          aria-label="Playback mode"
          disabled={!hasSteps}
        >
          <option value="LIVE">{fixturePreview ? "Current fixture state" : "Live source"}</option>
          <option value="REPLAY">Replay</option>
          <option value="SIMULATED">Fixture preview</option>
        </select>
        <select
          value={speed}
          data-testid="player-speed"
          aria-label="Playback speed"
          disabled={!hasSteps}
          onChange={(e) => { if (hasSteps) onSpeed(Number(e.target.value)); }}
        >
          <option value={1200}>0.5x</option>
          <option value={750}>1x</option>
          <option value={400}>2x</option>
        </select>
      </div>
    </div>
  );
}