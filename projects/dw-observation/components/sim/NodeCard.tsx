import type { SimNode, NodeState } from "@/lib/simRun";

type Props = {
  gateId: string;
  node: SimNode;
  state: NodeState;
  selected: boolean;
  onSelect: (gateId: string, nodeId: string) => void;
};

const STATE_LABEL: Record<NodeState, string> = {
  done: "DONE",
  active: "ACTIVE",
  future: "FUTURE",
};

/**
 * Runtime NODE card (corrected architect: node is the unit, not a task card).
 * Shows family / node type / authority boundary / artifact+runbook+event counts.
 */
export default function NodeCard({ gateId, node, state, selected, onSelect }: Props) {
  return (
    <article
      className={`sr-node-card ${state}${selected ? " selected" : ""}`}
      data-node-id={node.node_id}
      data-node-kind="runtime-node"
      data-active={state === "active" ? "true" : "false"}
      onClick={() => onSelect(gateId, node.node_id)}
    >
      <div className="sr-node-top">
        <span>{node.node_label ?? node.node_id}</span>
        <span>{STATE_LABEL[state]}</span>
      </div>
      <div className="sr-node-title">{node.title}</div>
      <div className="sr-node-id">{node.node_id}</div>
      <div className="sr-node-desc">{node.description}</div>
      <div className="sr-note-line">
        Family: <b>{node.family}</b> · Boundary: <b>{node.authority_boundary}</b>
      </div>
      <div className="sr-meta">
        <span className="sr-mini sr-family">{node.node_type}</span>
        <span className="sr-mini sr-artifacts">{node.artifacts.length} artifacts</span>
        <span className="sr-mini sr-history">{node.runbook.length} runbook</span>
        <span className="sr-mini">
          {node.taskcontroller_history.length} TC
        </span>
        <span className="sr-mini">
          {node.executor_history.length} EX
        </span>
      </div>
      <div className="sr-node-bottom">
        <div className="sr-metric">
          <b>{node.artifacts.length}</b>
          <span>artifacts</span>
        </div>
        <div className="sr-metric">
          <b>{node.taskcontroller_history.length}</b>
          <span>controller</span>
        </div>
        <div className="sr-metric">
          <b>{node.executor_history.length}</b>
          <span>executor</span>
        </div>
      </div>
    </article>
  );
}
