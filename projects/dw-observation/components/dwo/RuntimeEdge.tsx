import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

/**
 * RuntimeEdge — route/gate/fanout edge for the unified canvas.
 * Adapted from login-epic RuntimeEdge for UnifiedRuntimeEdge kinds.
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
              stroke: "var(--dwo-color-state-amber)",
              strokeWidth: 3,
              strokeDasharray: "6 4",
              animation: "runtime-edge-dash 0.8s linear infinite",
            }
          : {}),
      }}
    />
  );
}