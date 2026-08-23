import type { ReplayMode } from "@/lib/simRun";

type Props = {
  cursor: number;
  timelineLength: number;
  mode: ReplayMode;
  speed: number;
  playing: boolean;
  label: string;
  onFirst: () => void;
  onPrev: () => void;
  onPlayToggle: () => void;
  onNext: () => void;
  onLast: () => void;
  onScrub: (cursor: number) => void;
  onMode: (mode: ReplayMode) => void;
  onSpeed: (ms: number) => void;
};

const SPEEDS: { label: string; ms: number }[] = [
  { label: "0.5x", ms: 1200 },
  { label: "1x", ms: 750 },
  { label: "2x", ms: 400 },
];

/**
 * Player controller: transport buttons + scrubber + REPLAY/LIVE mode + speed.
 * Pure presentational; all handlers come from the parent.
 */
export default function ReplayControls({
  cursor,
  timelineLength,
  mode,
  speed,
  playing,
  label,
  onFirst,
  onPrev,
  onPlayToggle,
  onNext,
  onLast,
  onScrub,
  onMode,
  onSpeed,
}: Props) {
  return (
    <div className="sr-player">
      <div className="sr-controls">
        <button className="sr-btn" onClick={onFirst} title="First">
          ⏮
        </button>
        <button className="sr-btn" onClick={onPrev} title="Previous">
          ◀
        </button>
        <button
          className="sr-btn sr-primary"
          onClick={onPlayToggle}
          title={playing ? "Pause" : "Play"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <button className="sr-btn" onClick={onNext} title="Next">
          ▶|
        </button>
        <button className="sr-btn" onClick={onLast} title="Last">
          ⏭
        </button>
        <button
          className="sr-btn sr-live"
          onClick={() => onMode("LIVE")}
          title="Live simulation"
        >
          ● LIVE SIM
        </button>
      </div>
      <div className="sr-scrub">
        <div className="sr-scrub-info">
          <span>{label}</span>
          <span>
            {cursor + 1} / {timelineLength}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, timelineLength - 1)}
          value={cursor}
          onChange={(e) => onScrub(Number(e.target.value))}
        />
      </div>
      <div className="sr-selects">
        <select
          value={mode}
          onChange={(e) => onMode(e.target.value as ReplayMode)}
        >
          <option value="REPLAY">REPLAY</option>
          <option value="LIVE">LIVE SIM</option>
        </select>
        <select value={speed} onChange={(e) => onSpeed(Number(e.target.value))}>
          {SPEEDS.map((s) => (
            <option key={s.ms} value={s.ms}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
