"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  MarkerType,
  type EdgeProps,
} from "@xyflow/react";

export type GraphEdgeData = {
  label?: string;
  active?: boolean;
  [key: string]: unknown;
};

export default function RunGraphEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const d = data as GraphEdgeData;
  const edgeId = id.replace(/^e-/, "");
  const active = Boolean(d?.active);
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        data-testid="runflow-edge"
        data-edge-id={edgeId}
        markerEnd={`url(#react-flow__arrowclosed)`}
        style={{
          stroke: active ? "#5b9dff" : "#94a3b8",
          strokeWidth: active ? 2 : 1.2,
        }}
      />
      {d?.label && (
        <EdgeLabelRenderer>
          <div
            data-testid="runflow-edge-label"
            data-edge-id={edgeId}
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "all",
              fontSize: 10,
              color: active ? "#5b9dff" : "#94a3b8",
              background: "#0b0f17",
              border: "1px solid #1f2937",
              borderRadius: 4,
              padding: "1px 4px",
              whiteSpace: "nowrap",
            }}
          >
            {d.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
