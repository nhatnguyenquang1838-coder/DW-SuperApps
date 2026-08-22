"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { RunHierarchy } from "@/lib/observatory";
import RunGraphNodeCard from "@/components/RunGraphNodeCard";
import RunGraphEdge from "@/components/RunGraphEdge";

// M5 seq=3 (design-first, Context7 React Flow). Animated hierarchical run
// graph: every step is a card (custom node), connected by visible directional
// edges (ArrowClosed). Active card (#80) pulses; completed cards stable.
// Read-only: no drag/connect/select. Layout is deterministic from the
// RunHierarchy (NOT inferred, NOT a free-form LLM layout).

const nodeTypes = { graphNode: RunGraphNodeCard };
const edgeTypes = { graphEdge: RunGraphEdge };

// Deterministic column assignment: root left, chain middle, gates right branch.
function column(kind: string): number {
  if (kind === "root") return 0;
  if (kind === "gate") return 2;
  return 1; // node | issue
}

export default function RunGraphView({
  hierarchy,
  activeId,
}: {
  hierarchy: RunHierarchy;
  activeId?: string;
}) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const nodes: Node[] = hierarchy.nodes.map((n, i) => ({
      id: n.id,
      type: "graphNode",
      position: { x: column(n.kind) * 240, y: i * 84 },
      data: { node: n, active: activeId === n.id },
      draggable: false,
    }));

    const edges: Edge[] = hierarchy.connectors.map((c) => {
      const active = activeId === c.to || activeId === c.from;
      return {
        id: `e-${c.from}-${c.to}`,
        source: c.from,
        target: c.to,
        type: "graphEdge",
        label: c.label,
        animated: active,
        markerEnd: { type: MarkerType.ArrowClosed, color: active ? "#5b9dff" : "#94a3b8" },
        data: { label: c.label, active },
      };
    });

    return { rfNodes: nodes, rfEdges: edges };
  }, [hierarchy, activeId]);

  return (
    <div
      data-testid="run-graph-view"
      className="rounded-lg border border-edge bg-panel p-4"
    >
      <h2 className="mb-1 text-base font-semibold">Hierarchical run graph</h2>
      <p className="mb-3 text-xs text-muted">
        Source-backed nodes/edges (React Flow). Each card is a recorded
        step/gate/issue; edges are explicit, never inferred. Read-only.
      </p>
      <div style={{ height: 520 }} className="rounded border border-edge/60 bg-surface">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}
