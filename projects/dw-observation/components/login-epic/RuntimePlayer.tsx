import type { ReplayMode } from "@/lib/loginEpicRuntimeGraph";

/** RuntimePlayer — first/prev/play-pause/next/last/scrubber/speed/LIVE SIM. */
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
  mode: ReplayMode;
  speed: number;
  playing: boolean;
  label: string;
  onFirst: () => void;
  onPrev: () => void;
  onToggle: () => void;
  onNext: () => void;
  onLast: () => void;
  onScrub: (c: number) => void;
  onMode: (m: ReplayMode) => void;
  onSpeed: (ms: number) => void;
}) {
  return (
    <div className="leg-player" data-testid="runtime-player">
      <div className="leg-controls">
        <button className="leg-btn" data-testid="runtime-player-first" onClick={onFirst}>⏮</button>
        <button className="leg-btn" data-testid="runtime-player-prev" onClick={onPrev}>◀</button>
        <button className="leg-btn leg-primary" data-testid="runtime-player-play" onClick={onToggle}>
          {playing ? "❚❚" : "▶"}
        </button>
        <button className="leg-btn" data-testid="runtime-player-next" onClick={onNext}>▶|</button>
        <button className="leg-btn" data-testid="runtime-player-last" onClick={onLast}>⏭</button>
        <button className="leg-btn leg-live" data-testid="runtime-live-sim" onClick={() => onMode("LIVE_SIM")}>
          ● LIVE SIM
        </button>
      </div>
      <div className="leg-scrub">
        <div className="leg-scrub-info">
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
          data-testid="runtime-player-scrubber"
          onChange={(e) => onScrub(Number(e.target.value))}
        />
      </div>
      <div className="leg-selects">
        <select value={mode} onChange={(e) => onMode(e.target.value as ReplayMode)}>
          <option value="REPLAY">REPLAY</option>
          <option value="LIVE_SIM">LIVE SIM</option>
        </select>
        <select
          value={speed}
          data-testid="runtime-player-speed"
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
