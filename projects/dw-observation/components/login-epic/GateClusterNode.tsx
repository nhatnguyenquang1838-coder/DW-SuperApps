import type { RuntimeGate, GateId } from "@/lib/loginEpicRuntimeGraph";

/**
 * GateClusterNode — the large G0..G6 cluster container. Holds its runtime node
 * children (positioned by the canvas). data-testid carries the gate id.
 */
export default function GateClusterNode({
  data,
}: {
  data: { gate: RuntimeGate; state: "done" | "active" | "future" | "empty" };
}) {
  const { gate, state } = data;
  return (
    <div
      className={`leg-gate-cluster leg-gate-${state}`}
      data-testid="runtime-gate-cluster"
      data-gate-id={gate.id as GateId}
    >
      <div className="leg-gate-label">{gate.id}</div>
      <div className="leg-gate-sub">{gate.label}</div>
      <div className="leg-gate-summary">{gate.summary}</div>
      <div className="leg-gate-meta">
        <span>{gate.nodes.length} nodes</span>
        <span>{gate.gateArtifacts.length} artifacts</span>
      </div>
    </div>
  );
}
