import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

/**
 * RuntimeEdge — route/gate edge.
 *
 * Active route edges (the one at the current cursor) get the class
 * `runtime-active-edge` (hoisted onto the rendered `.react-flow__edge` wrapper by
 * React Flow) plus an explicit, deterministic animated yellow stroke so the "active
 * edge animation marker" is verifiable in the DOM without depending on the upstream
 * React Flow theme stylesheet. The class is the deterministic marker asserted by tests.
 */
export default function RuntimeEdge(props: EdgeProps) {
  const [path] = getBezierPath({
    sourceX: props.sourceX ?? 0,
    sourceY: props.sourceY ?? 0,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX ?? 0,
    targetY: props.targetY ?? 0,
    targetPosition: props.targetPosition,
  });
  const isActive = (props.data as { active?: boolean } | undefined)?.active === true;
  return (
    <BaseEdge
      id={props.id}
      path={path}
      markerEnd={props.markerEnd}
      className={isActive ? "runtime-active-edge" : undefined}
      style={{
        ...(props.style ?? {}),
        ...(isActive
          ? {
              stroke: "#ffd34d",
              strokeWidth: 3,
              strokeDasharray: "6 4",
              animation: "runtime-edge-dash 0.8s linear infinite",
            }
          : {}),
      }}
    />
  );
}
