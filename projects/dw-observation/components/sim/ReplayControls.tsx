import type { ReplayMode } from "@/lib/simRun";

type Props = {
  cursor: number;
  timelineLength: number;
  mode: ReplayMode;
  speed: number;
  playing: boolean;
  onFirst: () => void;
  onPrev: () => void;
  onPlayPause: () => void;
  onNext: () => void;
  onLast: () => void;
  onScrub: (value: number) => void;
  onModeChange: (mode: ReplayMode) => void;
  onSpeedChange: (speed: number) => void;
  playerLabel: string;
};

/** Replay transport: scrubber + first/prev/play/next/last + mode/speed. */
export default function ReplayControls(props: Props) {
  return (
    <div className="sr-player" data-testid="sr-player">
      <div className="sr-controls">
        <button className="sr-btn" data-testid="sr-first" onClick={props.onFirst}>⏮</button>
        <button className="sr-btn" data-testid="sr-prev" onClick={props.onPrev}>◀</button>
        <button className="sr-btn sr-primary" data-testid="sr-play" onClick={props.onPlayPause}>
          {props.playing ? "❚❚" : "▶"}
        </button>
        <button className="sr-btn" data-testid="sr-next" onClick={props.onNext}>▶|</button>
        <button className="sr-btn" data-testid="sr-last" onClick={props.onLast}>⏭</button>
      </div>
      <div className="sr-scrub">
        <div className="sr-scrub-info">
          <span data-testid="sr-player-label">{props.playerLabel}</span>
          <span data-testid="sr-player-count">
            {props.cursor + 1} / {props.timelineLength}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={props.timelineLength - 1}
          value={props.cursor}
          data-testid="sr-range"
          onChange={(e) => props.onScrub(Number(e.target.value))}
        />
      </div>
      <div className="sr-selects">
        <select
          data-testid="sr-mode"
          value={props.mode}
          onChange={(e) => props.onModeChange(e.target.value as ReplayMode)}
        >
          <option value="REPLAY">REPLAY</option>
          <option value="LIVE">LIVE</option>
        </select>
        <select
          data-testid="sr-speed"
          value={props.speed}
          onChange={(e) => props.onSpeedChange(Number(e.target.value))}
        >
          <option value={1600}>0.5×</option>
          <option value={900}>1×</option>
          <option value={500}>2×</option>
        </select>
      </div>
    </div>
  );
}
