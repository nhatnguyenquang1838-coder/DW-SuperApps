"use client";

import { computeNextFlow } from "@/lib/runtime/nextFlow";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";
import styles from "./NextFlowPanel.module.css";

/** Source-backed Next Flow projection. Never infers from visual position or guesses from sequence. */
export default function NextFlowPanel({ model }: { model: UnifiedRunWorkspaceModel }) {
  const projection = computeNextFlow(model);
  const statusColor: Record<string, string> = {
    RESOLVED: "var(--dwo-color-state-green)",
    UNKNOWN: "var(--dwo-color-state-amber)",
    BLOCKED: "var(--dwo-color-state-red)",
    CONFLICT: "var(--dwo-color-state-purple)",
  };
  const sourceUnavailable = projection.status === "UNKNOWN";

  return (
    <div className={`dwo-nextflow-panel ${styles.panel}`} data-testid="nextflow-panel" data-status={projection.status}>
      <div className="dwo-nextflow-label">Next Flow</div>
      <div className="dwo-nextflow-node" data-testid="nextflow-node">
        {projection.nextNodeId ?? <span className="dwo-unknown">UNKNOWN</span>}
      </div>
      <div className="dwo-nextflow-reason" data-testid="nextflow-reason">
        {projection.reason ?? <span className="dwo-unknown">UNKNOWN</span>}
      </div>
      {sourceUnavailable ? <p className={styles.guidance}>Sequence data is not available in this source, so the next step cannot be shown.</p> : null}
      {projection.blocker && <div className="dwo-nextflow-blocker" data-testid="nextflow-blocker">Blocker: {projection.blocker}</div>}
      <div className="dwo-nextflow-status" data-testid="nextflow-status" style={{ backgroundColor: statusColor[projection.status] ?? "transparent" }}>
        {projection.status} ({projection.source})
      </div>
      {sourceUnavailable ? (
        <details className={styles.details} aria-label="Source details">
          <summary>Source details</summary>
          <dl>
            <div><dt>Projection source</dt><dd>{projection.source}</dd></div>
            <div><dt>Projection status</dt><dd>{model.projectionStatus}</dd></div>
            <div><dt>Projection sync</dt><dd>{model.projectionSyncState ?? "Not provided"}</dd></div>
            <div><dt>Current sequence</dt><dd>{model.currentSequence ?? "No current sequence supplied"}</dd></div>
            <div><dt>Ordered source steps</dt><dd>{model.orderedSteps.length}</dd></div>
            <div><dt>Source digest</dt><dd>{model.sourceDigest ?? "Not provided"}</dd></div>
          </dl>
        </details>
      ) : null}
    </div>
  );
}