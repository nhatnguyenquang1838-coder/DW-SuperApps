import { Handle, Position } from "@xyflow/react";
import type { RuntimeNodeState } from "@/lib/runtime/unifiedRuntime";

/**
 * RuntimeNodeCard — one runtime node inside a Gate cluster.
 * Adapted to accept unified model node shape.
 */
export default function RuntimeNodeCard({
  data,
}: {
  data: {
    node: {
      id: string;
      title: string;
      family: string | null | undefined;
      nodeType: string | null | undefined;
      boundary: string | null | undefined;
      purpose: string | null | undefined;
      artifacts: string[];
      fileReads: string[];
      fileWrites: string[];
    };
    state: RuntimeNodeState;
    active: boolean;
    selected: boolean;
    boundary: string;
    onOpen: (path: string, kind: string) => void;
  };
}) {
  const { node, state, active, selected, boundary } = data;
  return (
    <div
      className={`leg-node leg-node-${state}${selected ? " selected" : ""}`}
      data-testid="runtime-node-card"
      data-node-id={node.id}
      data-boundary={boundary}
      data-active={active ? "true" : "false"}
    >
      <Handle type="target" position={Position.Left} />
      <div className="leg-node-top">
        <span>{node.family ?? "—"}</span>
        <span className="leg-state">{state.toUpperCase()}</span>
      </div>
      <div className="leg-node-title">{node.title}</div>
      <div className="leg-node-id">{node.id}</div>
      {node.purpose && (
        <div className="leg-node-purpose">{node.purpose}</div>
      )}
      <div className="leg-node-boundary">⌖ {boundary}</div>
      <div className="leg-node-meta">
        <span>{node.artifacts.length} art</span>
        <span>{node.fileReads.length} rd</span>
        <span>{node.fileWrites.length} wr</span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}