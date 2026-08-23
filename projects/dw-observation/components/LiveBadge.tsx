import { LiveState } from "@/lib/live";

// Read-only live-state indicator for the DW Run Observatory M2 live view.
// Surfaces the observer lifecycle (LIVE / CATCHING_UP / DEGRADED /
// PROJECTION_UNAVAILABLE) without any inferred authority or gate state.

const LABEL: Record<LiveState, { text: string; className: string }> = {
  UNAVAILABLE: { text: "unavailable", className: "bg-edge text-muted" },
  LIVE: { text: "live", className: "bg-green-500/20 text-green-400" },
  CATCHING_UP: { text: "catching up", className: "bg-amber-500/20 text-amber-400" },
  DEGRADED: { text: "degraded", className: "bg-amber-500/20 text-amber-400" },
  PROJECTION_UNAVAILABLE: {
    text: "projection unavailable",
    className: "bg-red-500/20 text-red-400",
  },
};

export default function LiveBadge({ state }: { state: LiveState }) {
  const { text, className } = LABEL[state];
  return (
    <span
      role="status"
      aria-live="polite"
      className={`rounded px-2 py-0.5 text-xs font-medium ${className}`}
    >
      {text}
    </span>
  );
}
