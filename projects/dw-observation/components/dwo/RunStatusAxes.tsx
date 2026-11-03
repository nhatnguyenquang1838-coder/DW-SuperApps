"use client";

import type {
  ProjectionSyncStatus,
  QualificationProjection,
  WorkspaceViewState,
} from "@/lib/dwo/qualificationProjection";
import styles from "./RunStatusAxes.module.css";

const syncGuidance: Record<ProjectionSyncStatus, string> = {
  LIVE: "Projection is synchronized with the available source.",
  SYNCING: "Projection is catching up with source data.",
  DEGRADED: "Projection data is delayed or incomplete.",
  GAP: "No synchronized projection is available for this view.",
};

const qualificationGuidance: Record<QualificationProjection["status"], string> = {
  UNKNOWN: "Not enough evidence to determine qualification.",
  QUALIFYING: "Qualification evidence is being evaluated.",
  QUALIFIED: "Receipt matches the current subject. Evidence only; does not grant execution authority.",
  FAILED: "Qualification checks did not pass.",
  DRIFTED: "Receipt does not match the current subject.",
};

export default function RunStatusAxes({
  projectionSync,
  view,
  qualification,
}: {
  projectionSync: ProjectionSyncStatus;
  view: WorkspaceViewState;
  qualification: QualificationProjection;
}) {
  const viewGuidance = view === "REPLAY"
    ? "Showing a selected historical view."
    : "Showing the current available view; this does not certify semantic qualification.";

  return (
    <section className={`dwo-status-axes ${styles.axes}`} data-testid="run-status-axes" aria-label="Run status axes">
      <div className={`dwo-status-axis ${styles.axis}`} data-axis="projection-sync" data-value={projectionSync} data-testid="axis-projection-sync">
        <span className={`dwo-status-axis-label ${styles.label}`}>Projection Sync</span>
        <strong className={`dwo-status-axis-value ${styles.value}`} data-status={projectionSync}>{projectionSync}</strong>
        <span className={styles.guidance}>{syncGuidance[projectionSync]}</span>
      </div>
      <div className={`dwo-status-axis ${styles.axis}`} data-axis="view" data-value={view} data-testid="axis-view">
        <span className={`dwo-status-axis-label ${styles.label}`}>View</span>
        <strong className={`dwo-status-axis-value ${styles.value}`} data-status={view}>{view}</strong>
        <span className={styles.guidance}>{viewGuidance}</span>
      </div>
      <div className={`dwo-status-axis dwo-status-axis--qualification ${styles.axis}`} data-axis="semantic-qualification" data-value={qualification.status} data-testid="axis-qualification">
        <span className={`dwo-status-axis-label ${styles.label}`}>Semantic Qualification</span>
        <strong className={`dwo-status-axis-value ${styles.value}`} data-status={qualification.status}>{qualification.status}</strong>
        <span className={styles.guidance}>{qualificationGuidance[qualification.status]}</span>
        {qualification.sourceRepository || qualification.sourceSha || qualification.durablePosition ? (
          <div className={styles.provenance} aria-label="Qualification provenance">
            <span className={styles.provenanceLabel}>Receipt source</span>
            <code>{qualification.sourceRepository ?? "Unknown repository"}</code>
            <code>{qualification.sourceSha ?? "Unknown source revision"}</code>
            <code>{qualification.durablePosition ?? "Unknown durable position"}</code>
          </div>
        ) : null}
      </div>
    </section>
  );
}
