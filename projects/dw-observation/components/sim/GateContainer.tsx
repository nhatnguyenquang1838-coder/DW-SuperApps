import { useState } from "react";
import type {
  SimGate,
  SimNode,
  NodeState,
  Selection,
  SimRun,
} from "@/lib/simRun";
import { nodeStateAt } from "@/lib/simRun";
import NodeCard from "./NodeCard";
import Connector from "./Connector";

type Props = {
  gate: SimGate;
  run: SimRun;
  cursor: number;
  active: boolean;
  selection: Selection;
  onSelectNode: (gateId: string, nodeId: string) => void;
  onSelectGate: (gateId: string) => void;
};

/**
 * Gate container: holds its node cards + connectors. Collapsible. The header
 * click selects the gate summary (alt-click) or toggles collapse.
 */
export default function GateContainer({
  gate,
  run,
  cursor,
  active,
  selection,
  onSelectNode,
  onSelectGate,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <section
      className={`sr-gate${collapsed ? " collapsed" : ""}${active ? " active" : ""}`}
      data-gate-id={gate.id}
    >
      <div
        className="sr-gate-head"
        onClick={(e) => {
          if (e.altKey) onSelectGate(gate.id);
          else setCollapsed((c) => !c);
        }}
      >
        <div>
          <div className="sr-gate-id">{gate.id}</div>
          <div className="sr-gate-label">{gate.label}</div>
        </div>
        <div className="sr-gate-summary">{gate.summary}</div>
        <div className="sr-gate-history">
          <span className="sr-count">{gate.nodes.length} NODES</span>
          <span className="sr-count">{gate.gate_artifacts.length} ARTIFACTS</span>
          <span className="sr-count">
            {gate.taskcontroller_history.length} TC EVENTS
          </span>
          <span className="sr-count">
            {gate.executor_history.length} EXEC EVENTS
          </span>
        </div>
        <span className="sr-chev">▼</span>
      </div>
      <div className="sr-gate-body">
        <div className="sr-nodes">
          {gate.nodes.map((n: SimNode, i: number) => {
            const state: NodeState = nodeStateAt(run, gate.id, n.node_id, cursor);
            const sel =
              selection.kind === "node" &&
              selection.gateId === gate.id &&
              selection.nodeId === n.node_id;
            return (
              <div className="sr-node-wrap" key={n.node_id}>
                <NodeCard
                  gateId={gate.id}
                  node={n}
                  state={state}
                  selected={sel}
                  onSelect={onSelectNode}
                />
                {i < gate.nodes.length - 1 && <Connector state={state} />}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
