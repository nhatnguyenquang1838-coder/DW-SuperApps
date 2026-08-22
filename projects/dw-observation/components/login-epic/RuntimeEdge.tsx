import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

/** RuntimeEdge — route/gate edge. Active edges animate (driven by `animated`). */
export default function RuntimeEdge(props: EdgeProps) {
  const [path] = getBezierPath({
    sourceX: props.sourceX ?? 0,
    sourceY: props.sourceY ?? 0,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX ?? 0,
    targetY: props.targetY ?? 0,
    targetPosition: props.targetPosition,
  });
  return (
    <BaseEdge
      id={props.id}
      path={path}
      markerEnd={props.markerEnd}
      style={props.style}
    />
  );
}
