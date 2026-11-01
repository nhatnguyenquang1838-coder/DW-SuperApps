"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  useReactFlow,
  useNodesInitialized,
  type Node as RFNode,
  type Edge as RFEdge,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type {
  UnifiedRunWorkspaceModel,
} from "@/lib/runtime/unifiedRuntime";
import { GATE_CHAIN } from "@/lib/loginEpicRuntimeGraph";
import GateClusterNode from "./GateClusterNode";
import RuntimeNodeCard from "./RuntimeNodeCard";
import RuntimeEdge from "./RuntimeEdge";
import MiniMap from "./MiniMap";
import { computeRuntimeGraphLayout } from "./graphLayout";

const nodeTypes: NodeTypes = {
  gateCluster: GateClusterNode,
  runtimeNode: RuntimeNodeCard,
};
const edgeTypes: EdgeTypes = { runtimeEdge: RuntimeEdge };

export default function RuntimeGraphCanvas({
  model,
  cursor,
  selection,
  followCursor,
  onSelectNode,
  onOpenArtifact,
  onUserViewportInteract,
}: {
  model: UnifiedRunWorkspaceModel;
  cursor: number;
  selection: { kind: "run" | "gate" | "node"; id: string };
  followCursor: boolean;
  onSelectNode: (nodeId: string) => void;
  onOpenArtifact: (path: string, kind: string) => void;
  onUserViewportInteract: () => void;
}) {
  const rf = useReactFlow();
  const nodesInitialized = useNodesInitialized();
  const activeIndex = model.currentSequence ?? cursor;
  const [dir, setDir] = useState<"LR" | "TD">("LR");
  const [form, setForm] = useState<"stack" | "grid">("grid");
  const [group, setGroup] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setDir(params.get("dir") === "TD" ? "TD" : "LR");
    setForm(params.get("form") === "stack" ? "stack" : "grid");
  }, []);

  const layout = useMemo(() => computeRuntimeGraphLayout(model.nodes, { direction: dir, form, grouped: group }), [model.nodes, dir, form, group]);

  // Build React Flow nodes: gate boxes first, then node cards.
  const rfNodes: RFNode[] = useMemo(() => {
    const out: RFNode[] = [];
    if (group) for (const cluster of layout.groups) {
      const nodes = model.nodes.filter((node) => cluster.nodeIds.includes(node.id));
      const gateLabel = GATE_CHAIN.includes(cluster.id as typeof GATE_CHAIN[number]) ? cluster.id.replace(/_/g, " ") : cluster.id;
      out.push({ id: `gate-${cluster.id}`, type: "gateCluster", position: { x: cluster.x, y: cluster.y }, data: { gateId: cluster.id, gateLabel, gateSummary: "", boundary: "", headerH: 48, nodeCount: nodes.length, artifactCount: nodes.reduce((a, n) => a + n.artifacts.length, 0), state: "UNKNOWN" }, draggable: false, selectable: false, zIndex: 0, style: { width: cluster.width, height: cluster.height, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12 } });
    }
    for (const n of model.nodes) {
      const rect = layout.nodes[n.id];
      const isActive = activeIndex >= 0 && model.orderedSteps[activeIndex]?.nodeId === n.id;
      out.push({ id: n.id, type: "runtimeNode", position: { x: rect.x, y: rect.y }, data: { node: n, state: n.gateState === "PASSED" ? "DONE" : n.gateState === "ACTIVE" ? "ACTIVE" : n.gateState === "WAITING" ? "WAITING" : n.gateState === "BLOCKED" ? "BLOCKED" : "UNKNOWN", active: isActive, selected: selection.kind === "node" && selection.id === n.id, boundary: n.authorityBoundary ?? "", onOpen: (path: string, kind: string) => onOpenArtifact(path, kind), direction: dir }, draggable: false, selectable: true, zIndex: 2, style: { width: rect.width } });
    }
    return out;
  }, [layout, group, activeIndex, selection, model.nodes, model.orderedSteps, onOpenArtifact, dir]);

  // Build edges from unified model edges.
  const rfEdges: RFEdge[] = useMemo(() => {
    return model.edges.map((e): RFEdge => {
      const isActive =
        e.kind === "ROUTE" &&
        activeIndex >= 0 &&
        model.orderedSteps[activeIndex]?.nodeId === e.source;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: "runtimeEdge",
        animated: false,
        zIndex: 0,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: {
          stroke:
            e.kind === "FANOUT"
              ? "rgba(140,147,166,0.25)"
              : isActive
                ? "var(--dwo-color-state-amber)"
                : "var(--dwo-color-accent-blue)",
          strokeWidth: e.kind === "FANOUT" ? 1 : 1.5,
          strokeDasharray: e.kind === "FANOUT" ? "3 4" : undefined,
        },
        data: { kind: e.kind, active: isActive },
        className: isActive ? "runtime-active-edge" : "",
      } as RFEdge;
    });
  }, [model.edges, activeIndex, model.orderedSteps]);

  const activeNodeId =
    activeIndex >= 0 ? model.orderedSteps[activeIndex]?.nodeId ?? null : null;

  const prevActive = useRef<string | null>(null);
  const previousLayout = useRef(`${dir}:${form}:${group}`);
  useEffect(() => {
    const nextLayout = `${dir}:${form}:${group}`;
    if (previousLayout.current === nextLayout || !nodesInitialized) return;
    previousLayout.current = nextLayout;
    rf.fitView({ duration: 0, minZoom: 0.35, maxZoom: 1.1 });
  }, [dir, form, group, nodesInitialized, rf]);
  useEffect(() => {
    if (!followCursor || !nodesInitialized) return;
    if (prevActive.current === activeNodeId) return;
    prevActive.current = activeNodeId;
    const node = rfNodes.find((n) => n.id === activeNodeId);
    if (node) {
      rf.setCenter(node.position.x + 144, node.position.y + 80, { zoom: 0.9, duration: 0 });
    }
  }, [followCursor, activeNodeId, rfNodes, rf, nodesInitialized]);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest(".dwo-layout-bar, .react-flow__node-runtimeNode")) return;
    onUserViewportInteract();
  };

  const onCenterGate = (gateId: string) => {
    const g = layout.groups.find((item) => item.id === gateId);
    if (g) rf.setCenter(g.x + g.width / 2, g.y + g.height / 2, { zoom: 0.7, duration: 400 });
  };

  return (
    <div className="dwo-canvas-wrap" data-testid="runtime-graph-canvas" data-follow-cursor={followCursor ? "true" : "false"} onPointerDownCapture={handlePointerDown} onWheelCapture={onUserViewportInteract}>
      <div className="dwo-layout-bar">
        <span className="dwo-layout-label">Layout</span>
        <button
          data-testid="layout-lr"
          className={dir === "LR" ? "on" : ""}
          onClick={() => setDir("LR")}
        aria-label="Layout left to right" aria-pressed={dir === "LR"}>LR</button>
        <button
          data-testid="layout-td"
          className={dir === "TD" ? "on" : ""}
          onClick={() => setDir("TD")}
        aria-label="Layout top to bottom" aria-pressed={dir === "TD"}>TD</button>
        <span className="dwo-layout-sep" />
        <button
          data-testid="layout-stack"
          className={form === "stack" ? "on" : ""}
          onClick={() => setForm("stack")}
        aria-label="Stack layout" aria-pressed={form === "stack"}>Stack</button>
        <button
          data-testid="layout-grid"
          className={form === "grid" ? "on" : ""}
          onClick={() => setForm("grid")}
        aria-label="Grid layout" aria-pressed={form === "grid"}>Grid</button>
        <span className="dwo-layout-sep" />
        <button
          data-testid="layout-group"
          className={group ? "on" : ""}
          onClick={() => setGroup((v) => !v)}
        aria-label="Group nodes by gate" aria-pressed={group}>Group</button>
      </div>

      <ReactFlow

        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        minZoom={0.35}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, n) => {
          if (n.type === "runtimeNode") onSelectNode(n.id);
        }}
        onMoveStart={(event) => {
          // React Flow supplies no input event for programmatic viewport moves.
          if (event) onUserViewportInteract();
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>

      <div className="dwo-zoombar">
        <button data-testid="runtime-zoom-in" onClick={() => rf.zoomIn()}>+</button>
        <button data-testid="runtime-zoom-out" onClick={() => rf.zoomOut()}>−</button>
        <button data-testid="runtime-fit" onClick={() => rf.fitView({ duration: 300 })}>Fit</button>
        <button
          data-testid="runtime-reset"
          onClick={() => { rf.setViewport({ x: 0, y: 0, zoom: 1 }); }}
        >Reset</button>
      </div>

      <MiniMap
        gateChain={GATE_CHAIN.filter((g) =>
          model.nodes.some((n) => n.gateId === g),
        )}
        activeGateId={activeNodeId ? model.nodes.find((n) => n.id === activeNodeId)?.gateId ?? null : null}
        onCenterGate={onCenterGate}
      />
    </div>
  );
}