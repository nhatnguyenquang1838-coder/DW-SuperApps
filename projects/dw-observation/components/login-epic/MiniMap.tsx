import type { LoginEpicRun, GateId } from "@/lib/loginEpicRuntimeGraph";
import { GATE_CHAIN } from "@/lib/loginEpicRuntimeGraph";

/**
 * MiniMap — compact overview of the 7 gate clusters. Clicking a gate requests
 * centering on that gate's first node (used for follow-cursor / navigation).
 */
export default function MiniMap({
  run,
  activeGateId,
  onCenterGate,
}: {
  run: LoginEpicRun;
  activeGateId: GateId | null;
  onCenterGate: (gateId: GateId) => void;
}) {
  const order = GATE_CHAIN.filter((g) => run.gates.some((x) => x.id === g));
  return (
    <div className="leg-minimap" data-testid="runtime-minimap">
      {order.map((g) => {
        const gate = run.gates.find((x) => x.id === g)!;
        return (
          <button
            key={g}
            className={`leg-mini-gate${activeGateId === g ? " active" : ""}`}
            onClick={() => onCenterGate(g)}
            title={gate.label}
          >
            {g}
          </button>
        );
      })}
    </div>
  );
}
