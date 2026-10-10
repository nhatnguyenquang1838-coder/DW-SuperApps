import type { RuntimeNodeState } from "@/lib/runtime/unifiedRuntime";

/** Human-readable authority-boundary label from the boundary token. */
const BOUNDARY_LABELS: Record<string, string> = {
  read_only: "read_only · G0",
  g2_execution_boundary: "product/ui · G2",
  g3_pr_boundary: "code_review · G3",
  g4_merge_boundary: "merge_control · G4",
  g5_deploy_boundary: "backend/api · G5",
  g6_production_boundary: "client/api · G6",
};

/**
 * GateClusterNode — background box for one gate cluster.
 * Adapted to accept unified model boundary/state strings.
 */
export default function GateClusterNode({
  data,
}: {
  data: {
    gateId: string;
    gateLabel: string;
    gateSummary: string;
    boundary: string;
    headerH: number;
    nodeCount: number;
    artifactCount: number;
    state: RuntimeNodeState;
  };
}) {
  const { gateId, gateLabel, boundary, headerH, nodeCount, artifactCount, state } = data;
  const label = BOUNDARY_LABELS[boundary] ?? boundary;
  return (
    <div
      className={`leg-gate-cluster leg-gate-${state} leg-boundary-${boundary}`}
      data-testid="runtime-gate-cluster"
      data-gate-id={gateId}
      data-boundary={boundary}
    >
      <div className="leg-gate-banner" data-boundary={boundary} style={{ height: headerH }}>
        <div className="leg-gate-banner-top">
          <span className="leg-gate-id">{gateId}</span>
          <span className="leg-gate-band" data-boundary={boundary}>{label}</span>
          <span className="leg-gate-state">{state.toUpperCase()}</span>
        </div>
        <div className="leg-gate-banner-sub">{gateLabel}</div>
        <div className="leg-gate-banner-meta">
          <span>{nodeCount} nodes</span>
          <span>{artifactCount} artifacts</span>
        </div>
      </div>
    </div>
  );
}