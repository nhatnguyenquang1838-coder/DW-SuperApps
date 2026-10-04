"use client";

import { computeNextFlow } from "@/lib/runtime/nextFlow";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

/**
 * NextFlowPanel — source-backed Next Flow projection.
 *
 * Uses computeNextFlow() to derive the projection from runtime evidence
 * (orderedSteps + currentSequence), with fail-closed UNKNOWN/CONFLICT/BLOCKED
 * states. Never infers from visual position, never guesses from sequence.
 */
export default function NextFlowPanel({ model }: { model: UnifiedRunWorkspaceModel }) {
  const projection = computeNextFlow(model);

  const statusColor: Record<string, string> = {
    RESOLVED: "var(--dwo-color-state-green)",
    UNKNOWN: "var(--dwo-color-state-amber)",
    BLOCKED: "var(--dwo-color-state-red)",
    CONFLICT: "var(--dwo-color-state-purple)",
  };

  return (
    <div
      className="dwo-nextflow-panel"
      data-testid="nextflow-panel"
      data-status={projection.status}
    >
      <div className="dwo-nextflow-label">Next Flow</div>
      <div className="dwo-nextflow-node" data-testid="nextflow-node">
        {projection.nextNodeId ?? <span className="dwo-unknown">UNKNOWN</span>}
      </div>
      <div className="dwo-nextflow-reason" data-testid="nextflow-reason">
        {projection.reason ?? <span className="dwo-unknown">UNKNOWN</span>}
      </div>
      {projection.blocker && (
        <div className="dwo-nextflow-blocker" data-testid="nextflow-blocker">
          Blocker: {projection.blocker}
        </div>
      )}
      <div
        className="dwo-nextflow-status"
        data-testid="nextflow-status"
        style={{ backgroundColor: statusColor[projection.status] ?? "transparent" }}
      >
        {projection.status} ({projection.source})
      </div>
    </div>
  );
}