"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  useReactFlow,
  type Node as RFNode,
  type Edge as RFEdge,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type {
  LoginEpicRun,
  GateId,
  RuntimeNode,
  NodeState,
} from "@/lib/loginEpicRuntimeGraph";
import {
  getActiveRoute,
  getNodeState,
  getGateState,
  buildGateEdges,
  buildRouteEdges,
  makeArtifactPreview,
} from "@/lib/loginEpicRuntimeGraph";
import GateClusterNode from "./GateClusterNode";
import RuntimeNodeCard from "./RuntimeNodeCard";
import RuntimeEdge from "./RuntimeEdge";

const nodeTypes: NodeTypes = {
  gateCluster: GateClusterNode,
  runtimeNode: RuntimeNodeCard,
};
const edgeTypes: EdgeTypes = { runtimeEdge: RuntimeEdge };

const GATE_W = 360;
const GATE_GAP = 120;
const NODE_GAP_Y = 14;

export default function RuntimeGraphCanvas({
  run,
  cursor,
  selection,
  followCursor,
  onSelectNode,
  onOpenArtifact,
}: {
  run: LoginEpicRun;
  cursor: number;
  selection: { kind: "run" | "gate" | "node"; id: string };
  followCursor: boolean;
  onSelectNode: (nodeId: string) => void;
  onOpenArtifact: (path: string, kind: string) => void;
}) {
  const rf = useReactFlow();

  // Build nodes: one gate-cluster node per gate (positioned) + runtime node cards inside.
  const rfNodes: RFNode[] = useMemo(() => {
    const out: RFNode[] = [];
    run.gates.forEach((gate, gi) => {
      const gx = 40 + gi * (GATE_W + GATE_GAP);
      const gy = 40;
      const gateState = getGateState(run, gate.id, cursor);
      out.push({
        id: `gate-${gate.id}`,
        type: "gateCluster",
        position: { x: gx, y: gy },
        data: { gate, state: gateState },
        draggable: false,
        selectable: false,
        style: {
          width: GATE_W,
          height: 520,
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 12,
        },
      });
      gate.nodes.forEach((n: RuntimeNode, ni) => {
        const state: NodeState = getNodeState(run, n.id, cursor);
        const nx = gx + 16;
        const ny = gy + 70 + ni * (150 + NODE_GAP_Y);
        out.push({
          id: n.id,
          type: "runtimeNode",
          position: { x: nx, y: ny },
          data: {
            node: n,
            state,
            active: state === "active",
            selected: selection.kind === "node" && selection.id === n.id,
            onOpen: (path: string, kind: string) => onOpenArtifact(path, kind),
          },
          draggable: false,
          selectable: true,
        });
      });
    });
    return out;
  }, [run, cursor, selection]);

  // Determine active gate for minimap + label.
  const active = getActiveRoute(run, cursor);
  const activeGateId: GateId | null = active ? active.gate_id : null;

  // Build edges: gate dependency arrows (G0->G6) + route arrows (run.route).
  const rfEdges: RFEdge[] = useMemo(() => {
    const gateEdges = buildGateEdges(run).map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: "runtimeEdge",
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      style: { stroke: "#6ca9ff", strokeWidth: 2 },
      data: { kind: "gate" },
    }));
    const active = getActiveRoute(run, cursor);
    const routeEdges = buildRouteEdges(run).map((e, i) => {
      const isActive = i === cursor;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: "runtimeEdge",
        animated: isActive,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        style: {
          stroke: isActive ? "#ffd34d" : "#8a93a6",
          strokeWidth: isActive ? 3 : 1.5,
          opacity: isActive ? 1 : 0.6,
        },
        data: { kind: "route", active: isActive },
        className: isActive ? "runtime-active-edge" : "",
      } as RFEdge;
    });
    return [...gateEdges, ...routeEdges];
  }, [run, cursor, active]); // eslint-disable-line react-hooks/exhaustive-deps

  // Follow cursor: center viewport on the active node.
  const prevActive = useRef<string | null>(null);
  useEffect(() => {
    if (!followCursor) return;
    const activeNodeId = active.node_id;
    if (prevActive.current === activeNodeId) return;
    prevActive.current = activeNodeId;
    const node = rfNodes.find((n) => n.id === activeNodeId);
    if (node) {
      const t = setTimeout(() => rf.setCenter(node.position.x + 100, node.position.y + 60, { zoom: 0.85, duration: 400 }), 60);
      return () => clearTimeout(t);
    }
  }, [followCursor, active.node_id, rfNodes, rf]); // eslint-disable-line react-hooks/exhaustive-deps

  const onCenterGate = (gateId: GateId) => {
    const gate = run.gates.find((g) => g.id === gateId);
    if (!gate || !gate.nodes[0]) return;
    const node = rfNodes.find((n) => n.id === gate.nodes[0].id);
    if (node) rf.setCenter(node.position.x + 100, node.position.y + 60, { zoom: 0.85, duration: 400 });
  };

  return (
    <div className="leg-canvas-wrap" data-testid="runtime-graph-canvas">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, n) => {
          if (n.type === "runtimeNode") onSelectNode(n.id);
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>

      <div className="leg-zoombar">
        <button data-testid="runtime-zoom-in" onClick={() => rf.zoomIn()}>+</button>
        <button data-testid="runtime-zoom-out" onClick={() => rf.zoomOut()}>−</button>
        <button data-testid="runtime-fit" onClick={() => rf.fitView({ duration: 300 })}>Fit</button>
        <button
          data-testid="runtime-reset"
          onClick={() => {
            rf.setViewport({ x: 0, y: 0, zoom: 1 });
          }}
        >
          Reset
        </button>
      </div>

      <MiniMapWrapper run={run} activeGateId={activeGateId} onCenterGate={onCenterGate} />
    </div>
  );
}

// Local import kept at bottom to avoid a circular appearance at top.
import MiniMap from "./MiniMap";
function MiniMapWrapper(props: {
  run: LoginEpicRun;
  activeGateId: GateId | null;
  onCenterGate: (g: GateId) => void;
}) {
  return <MiniMap {...props} />;
}

// re-export to keep preview helper discoverable for tests
export { makeArtifactPreview };
