"use client";

import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

/**
 * NextFlowPanel — source-backed Next Flow projection.
 *
 * Derives next node from orderedSteps + currentSequence.
 * When source data is missing, renders UNKNOWN / BLOCKED explicitly
 * (never fabricates a next node).
 */
export default function NextFlowPanel({ model }: { model: UnifiedRunWorkspaceModel }) {
  const current = model.currentSequence;
  const steps = model.orderedSteps;

  let nextNodeId: string | null = null;
  let reason: string | null = null;
  let blocker: string | null = null;

  if (current === null || current === undefined) {
    reason = "No current sequence — awaiting source data";
  } else if (current < steps.length - 1) {
    nextNodeId = steps[current + 1]?.nodeId ?? null;
    reason = nextNodeId ? `Step ${current + 1} → ${current + 2}` : null;
  } else {
    reason = "At final step";
  }

  const status: "RESOLVED" | "UNKNOWN" | "BLOCKED" | "CONFLICT" =
    nextNodeId !== null ? "RESOLVED" : reason === "No current sequence — awaiting source data" ? "UNKNOWN" : "BLOCKED";

  return (
    <div className="dwo-nextflow-panel" data-testid="nextflow-panel" data-status={status}>
      <div className="dwo-nextflow-label">Next Flow</div>
      <div className="dwo-nextflow-node" data-testid="nextflow-node">
        {nextNodeId ?? <span className="dwo-unknown">UNKNOWN</span>}
      </div>
      <div className="dwo-nextflow-reason" data-testid="nextflow-reason">
        {reason ?? <span className="dwo-unknown">UNKNOWN</span>}
      </div>
      {blocker && (
        <div className="dwo-nextflow-blocker" data-testid="nextflow-blocker">
          Blocker: {blocker}
        </div>
      )}
      <div className="dwo-nextflow-status" data-testid="nextflow-status">
        {status}
      </div>
    </div>
  );
}