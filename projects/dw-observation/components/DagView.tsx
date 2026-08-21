"use client";

import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

type Props = {
  gates: Record<string, Record<string, unknown>>;
  nodes: Record<string, Record<string, unknown>>;
};

// G3 correction #1: React Flow DAG, read-only.
// - nodesAreDraggable=false, nodesConnectable=false, elementsSelectable=false,
//   edgesFocusable=false, zoomOnDoubleClick=false, panOnDrag only (no editing).
// - NO edges are invented: absent relationships stay absent (no inferred edge).
//   Gates and DAG nodes are rendered as isolated nodes.
export default function DagView({ gates, nodes }: Props) {
  const rfNodes = useMemo(() => {
    const items: Array<{ id: string; type: string; label: string; sub: string }> = [];
    for (const [name, g] of Object.entries(gates)) {
      const status = typeof g.status === "string" ? (g.status as string) : "unknown";
      items.push({ id: `gate:${name}`, type: "gate", label: name, sub: status });
    }
    for (const [name, n] of Object.entries(nodes)) {
      const status = typeof n.status === "string" ? (n.status as string) : "unknown";
      items.push({ id: `node:${name}`, type: "node", label: name, sub: status });
    }
    return items.map((it, i) => ({
      id: it.id,
      position: { x: 40 + (i % 3) * 260, y: 40 + Math.floor(i / 3) * 110 },
      data: { label: `${it.type === "gate" ? "GATE " : "NODE "}${it.label} · ${it.sub}` },
      // read-only: no draggable/connectable flags -> React Flow defaults are
      // overridden below via props; keep node data immutable.
    }));
  }, [gates, nodes]);

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <h2 className="mb-1 text-base font-semibold">Read-only DAG</h2>
      <p className="mb-3 text-xs text-muted">
        Rendered from explicitly recorded gates/nodes. No edges are inferred.
        Non-draggable · non-connectable · non-editable.
      </p>
      <div style={{ height: 320 }} className="rounded border border-edge/60 bg-surface">
        <ReactFlow
          nodes={rfNodes}
          edges={[]}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}
