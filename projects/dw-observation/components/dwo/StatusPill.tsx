import React from "react";

type StatusKey =
  | "RESOLVED"
  | "UNKNOWN_UNRESOLVED"
  | "CONFLICT"
  | "UNAVAILABLE"
  | "ACTIVE"
  | "WAITING"
  | "BLOCKED"
  | "COMPLETED"
  | "DEGRADED";

interface StatusPillProps {
  status: StatusKey | string;
  className?: string;
}

const statusColors: Record<string, React.CSSProperties> = {
  RESOLVED: {
    background: "var(--dwo-color-state-green)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-green)",
  },
  UNKNOWN_UNRESOLVED: {
    background: "var(--dwo-color-state-amber)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-amber)",
  },
  CONFLICT: {
    background: "var(--dwo-color-state-red)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-red)",
  },
  UNAVAILABLE: {
    background: "var(--dwo-color-text-muted)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-text-muted)",
  },
  ACTIVE: {
    background: "var(--dwo-color-accent-blue)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-accent-blue)",
  },
  WAITING: {
    background: "var(--dwo-color-state-purple)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-purple)",
  },
  BLOCKED: {
    background: "var(--dwo-color-state-red)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-red)",
  },
  COMPLETED: {
    background: "var(--dwo-color-state-green)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-green)",
  },
  DEGRADED: {
    background: "var(--dwo-color-state-amber)",
    color: "var(--dwo-color-bg-canvas)",
    borderColor: "var(--dwo-color-state-amber)",
  },
};

export default function StatusPill({ status, className = "" }: StatusPillProps) {
  const style = statusColors[status] ?? statusColors.UNAVAILABLE;
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide ${className}`}
      style={style}
    >
      {status}
    </span>
  );
}
