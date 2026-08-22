import { Handle, Position } from "@xyflow/react";
import type { RuntimeNode, NodeState } from "@/lib/loginEpicRuntimeGraph";

/**
 * RuntimeNodeCard — one runtime node inside a Gate cluster. Shows family/type/
 * boundary + counts. data-testid carries node id for deterministic tests.
 */
export default function RuntimeNodeCard({
  data,
}: {
  data: {
    node: RuntimeNode;
    state: NodeState;
    active: boolean;
    selected: boolean;
    onOpen: (path: string, kind: string) => void;
  };
}) {
  const { node, state, active, selected } = data;
  return (
    <div
      className={`leg-node leg-node-${state}${selected ? " selected" : ""}`}
      data-testid="runtime-node-card"
      data-node-id={node.id}
      data-active={active ? "true" : "false"}
    >
      <Handle type="target" position={Position.Left} />
      <div className="leg-node-top">
        <span>{node.family}</span>
        <span className="leg-state">{state.toUpperCase()}</span>
      </div>
      <div className="leg-node-title">{node.title}</div>
      <div className="leg-node-id">{node.id}</div>
      <div className="leg-node-purpose">{node.purpose}</div>
      <div className="leg-node-meta">
        <span>{node.artifacts.length} art</span>
        <span>{node.fileReads.length} rd</span>
        <span>{node.fileWrites.length} wr</span>
        <span>{node.taskControllerHistory.length} TC</span>
        <span>{node.executorHistory.length} EX</span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
