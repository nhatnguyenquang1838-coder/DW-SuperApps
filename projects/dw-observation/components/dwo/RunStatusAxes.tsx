"use client";

import type {
  ProjectionSyncStatus,
  QualificationProjection,
  WorkspaceViewState,
} from "@/lib/dwo/qualificationProjection";

export default function RunStatusAxes({
  projectionSync,
  view,
  qualification,
}: {
  projectionSync: ProjectionSyncStatus;
  view: WorkspaceViewState;
  qualification: QualificationProjection;
}) {
  return (
    <section className="dwo-status-axes" data-testid="run-status-axes" aria-label="Run status axes">
      <div
        className="dwo-status-axis"
        data-axis="projection-sync"
        data-value={projectionSync}
        data-testid="axis-projection-sync"
      >
        <span className="dwo-status-axis-label">Projection Sync</span>
        <strong className="dwo-status-axis-value">{projectionSync}</strong>
      </div>
      <div
        className="dwo-status-axis"
        data-axis="view"
        data-value={view}
        data-testid="axis-view"
      >
        <span className="dwo-status-axis-label">View</span>
        <strong className="dwo-status-axis-value">{view}</strong>
      </div>
      <div
        className="dwo-status-axis dwo-status-axis--qualification"
        data-axis="semantic-qualification"
        data-value={qualification.status}
        data-testid="axis-qualification"
      >
        <span className="dwo-status-axis-label">Semantic Qualification</span>
        <strong className="dwo-status-axis-value">{qualification.status}</strong>
        {qualification.status === "QUALIFIED" ? (
          <span className="dwo-status-axis-note">Evidence only; does not grant execution authority.</span>
        ) : null}
        {qualification.sourceSha && qualification.durablePosition ? (
          <span className="dwo-status-axis-provenance">
            {qualification.sourceRepository ?? "source"}@{qualification.sourceSha.slice(0, 12)} · {qualification.durablePosition}
          </span>
        ) : null}
      </div>
    </section>
  );
}
