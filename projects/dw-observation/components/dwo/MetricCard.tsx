import React from "react";

interface MetricCardProps {
  label: string;
  value: string | number | null;
  status?: "resolved" | "warning" | "error" | "info" | "unknown";
  sub?: string;
  className?: string;
}

const statusAccent: Record<string, string> = {
  resolved: "var(--color-green)",
  warning: "var(--color-amber)",
  error: "var(--color-red)",
  info: "var(--color-accent)",
  unknown: "var(--color-text-muted)",
};

export default function MetricCard({ label, value, status, sub, className = "" }: MetricCardProps) {
  const accent = status ? (statusAccent[status] ?? statusAccent.unknown) : "var(--color-accent)";
  return (
    <div
      className={`rounded-lg border p-4 ${className}`}
      style={{ borderColor: "var(--color-border)", background: "var(--color-surface)" } as React.CSSProperties}
    >
      <div className="text-xs uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold" style={{ color: accent }}>
        {value ?? "—"}
      </div>
      {sub && (
        <div className="mt-1 text-xs" style={{ color: "var(--color-text-faint)" }}>
          {sub}
        </div>
      )}
    </div>
  );
}