"use client";

import { readDashboardProjection, type DashboardProjection } from "@/lib/dashboard/readDashboardProjection";

interface DashboardProps {
  projection: DashboardProjection;
}

export default function Dashboard({ projection }: DashboardProps) {
  const { taskCount, runCounts, unresolvedCount, authorityWaitCount, degradedSourceCount, recentActivity, needsAttention } = projection;

  const healthy = !taskCount && !unresolvedCount && !degradedSourceCount && needsAttention.length === 0;
  const attention = unresolvedCount !== null && unresolvedCount > 0;
  const degraded = degradedSourceCount !== null && degradedSourceCount > 0;

  return (
    <div className="dwo-dashboard" data-testid="dashboard">
      <h2 className="dwo-h2">Dashboard</h2>
      <div className="dwo-dashboard-grid">
        <div className="dwo-dashboard-card" data-state={healthy ? "healthy" : attention ? "attention" : degraded ? "degraded" : "unknown"}>
          <span className="dwo-dashboard-label">Tasks</span>
          <span className="dwo-dashboard-value">{taskCount ?? "UNAVAILABLE"}</span>
        </div>
        <div className="dwo-dashboard-card" data-state={healthy ? "healthy" : attention ? "attention" : degraded ? "degraded" : "unknown"}>
          <span className="dwo-dashboard-label">Unresolved</span>
          <span className="dwo-dashboard-value">{unresolvedCount ?? "UNAVAILABLE"}</span>
        </div>
        <div className="dwo-dashboard-card" data-state={healthy ? "healthy" : attention ? "attention" : degraded ? "degraded" : "unknown"}>
          <span className="dwo-dashboard-label">Authority Waits</span>
          <span className="dwo-dashboard-value">{authorityWaitCount ?? "UNAVAILABLE"}</span>
        </div>
        <div className="dwo-dashboard-card" data-state={healthy ? "healthy" : attention ? "attention" : degraded ? "degraded" : "unknown"}>
          <span className="dwo-dashboard-label">Degraded Sources</span>
          <span className="dwo-dashboard-value">{degradedSourceCount ?? "UNAVAILABLE"}</span>
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