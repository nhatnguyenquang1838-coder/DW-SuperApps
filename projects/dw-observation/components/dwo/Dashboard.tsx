"use client";

import { type DashboardProjection } from "@/lib/dashboard/readDashboardProjection";

interface DashboardProps {
  projection: DashboardProjection;
}

/**
 * State semantics (TECH_SPEC §4):
 *  - unavailable (source down) must NOT render as 0;
 *  - 0 (source up, genuinely nothing) must NOT render as healthy-by-default;
 *  - a degraded or unknown source must be visibly distinct from a healthy one.
 */
function stateFor(
  count: number | null,
  degraded: boolean,
): "healthy" | "attention" | "degraded" | "unknown" {
  if (count === null) return degraded ? "degraded" : "unknown";
  if (degraded) return "degraded";
  if (count > 0) return "attention";
  return "healthy"; // count === 0, source affirmatively reported zero
}

export default function Dashboard({ projection }: DashboardProps) {
  const {
    taskCount,
    activeCount,
    waitingCount,
    blockedCount,
    completedCount,
    authorityWaitCount,
    degradedSourceCount,
    recentActivity,
    needsAttention,
  } = projection;

  const anyDegraded = degradedSourceCount !== null && degradedSourceCount > 0;

  const bucketRows: Array<{
    label: string;
    count: number | null;
    state: "healthy" | "attention" | "degraded" | "unknown";
  }> = [
    { label: "Active", count: activeCount, state: stateFor(activeCount, anyDegraded) },
    { label: "Waiting", count: waitingCount, state: stateFor(waitingCount, anyDegraded) },
    { label: "Blocked", count: blockedCount, state: stateFor(blockedCount, anyDegraded) },
    { label: "Completed", count: completedCount, state: stateFor(completedCount, anyDegraded) },
  ];

  return (
    <div className="dwo-dashboard" data-testid="dashboard">
      <h2 className="dwo-h2">Dashboard</h2>

      {/* Four-bucket population model — source-backed */}
      <div className="dwo-dashboard-grid">
        {bucketRows.map((b) => (
          <div
            key={b.label}
            className="dwo-dashboard-card"
            data-state={b.state}
          >
            <span className="dwo-dashboard-label">{b.label}</span>
            <span className="dwo-dashboard-value">
              {b.count ?? "UNAVAILABLE"}
            </span>
          </div>
        ))}
      </div>

      {/* Source health */}
      <div className="dwo-dashboard-grid" style={{ marginTop: 16 }}>
        <div
          className="dwo-dashboard-card"
          data-state={stateFor(taskCount, anyDegraded)}
        >
          <span className="dwo-dashboard-label">Tasks</span>
          <span className="dwo-dashboard-value">
            {taskCount ?? "UNAVAILABLE"}
          </span>
        </div>
        <div
          className="dwo-dashboard-card"
          data-state={stateFor(authorityWaitCount, anyDegraded)}
        >
          <span className="dwo-dashboard-label">Authority Waits</span>
          <span className="dwo-dashboard-value">
            {authorityWaitCount ?? "UNAVAILABLE"}
          </span>
        </div>
        <div
          className="dwo-dashboard-card"
          data-state={stateFor(degradedSourceCount, true)}
        >
          <span className="dwo-dashboard-label">Degraded Sources</span>
          <span className="dwo-dashboard-value">
            {degradedSourceCount ?? "UNAVAILABLE"}
          </span>
        </div>
      </div>

      {needsAttention.length > 0 && (
        <div className="dwo-dashboard-attention" data-testid="dashboard-attention">
          <h3 className="dwo-h3">Needs Attention</h3>
          {needsAttention.map((item, i) => (
            <div key={i} className="dwo-dashboard-item">{JSON.stringify(item)}</div>
          ))}
        </div>
      )}
      {recentActivity.length > 0 && (
        <div className="dwo-dashboard-activity">
          <h3 className="dwo-h3">Recent Activity</h3>
          {recentActivity.map((a, i) => (
            <div key={i} className="dwo-dashboard-item">{JSON.stringify(a)}</div>
          ))}
        </div>
      )}
    </div>
  );
}