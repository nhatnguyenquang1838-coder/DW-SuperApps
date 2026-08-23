import type { GateId } from "@/lib/loginEpicRuntimeGraph";

/** Human-readable authority-boundary label from the fixture boundary token. */
const BOUNDARY_LABELS: Record<string, string> = {
  read_only: "read_only · G0",
  g2_execution_boundary: "product/ui · G2",
  g3_pr_boundary: "code_review · G3",
  g4_merge_boundary: "merge_control · G4",
  g5_deploy_boundary: "backend/api · G5",
  g6_production_boundary: "client/api · G6",
};

/**
 * GateBoxNode — background box for one gate. Renders ONLY the container + a
 * fixed-height (HEADER_H) top banner holding all gate info (boundary colour +
 * gate id/label/summary/meta). Node cards are positioned below HEADER_H by the
 * layout engine, so gate info NEVER overlaps node content. The banner's height
 * is locked via inline style + CSS so it cannot grow into the node area.
 */
export default function GateClusterNode({
  data,
}: {
  data: {
    gateId: GateId;
    gateLabel: string;
    gateSummary: string;
    boundary: string;
    headerH: number;
    nodeCount: number;
    artifactCount: number;
    state: "done" | "active" | "future" | "empty";
  };
}) {
  const { gateId, gateLabel, gateSummary, boundary, headerH, nodeCount, artifactCount, state } = data;
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
        <div className="leg-gate-banner-sub">{gateLabel} · {gateSummary}</div>
        <div className="leg-gate-banner-meta">
          <span>{nodeCount} nodes</span>
          <span>{artifactCount} artifacts</span>
        </div>
      </div>
    </div>
  );
}
