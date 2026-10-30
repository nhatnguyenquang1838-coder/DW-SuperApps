/**
 * MiniMap — compact overview of gate clusters.
 * Accepts string gate IDs (unified model) instead of GateId enum.
 */
export default function MiniMap({
  gateChain,
  activeGateId,
  onCenterGate,
}: {
  gateChain: string[];
  activeGateId: string | null;
  onCenterGate: (gateId: string) => void;
}) {
  return (
    <div className="leg-minimap" data-testid="runtime-minimap">
      {gateChain.map((g) => (
        <button
          key={g}
          className={`leg-mini-gate${activeGateId === g ? " active" : ""}`}
          onClick={() => onCenterGate(g)}
          title={g}
        >
          {g}
        </button>
      ))}
    </div>
  );
}