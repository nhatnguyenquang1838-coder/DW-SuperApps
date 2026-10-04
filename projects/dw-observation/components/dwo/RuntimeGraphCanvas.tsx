"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  UnifiedRunWorkspaceModel,
  UnifiedRuntimeNode,
  WorkspaceMode,
} from "@/lib/runtime/unifiedRuntime";
import { GATE_CHAIN } from "@/lib/loginEpicRuntimeGraph";
import GateClusterNode from "./GateClusterNode";
import RuntimeNodeCard from "./RuntimeNodeCard";
import RuntimeEdge from "./RuntimeEdge";
import MiniMap from "./MiniMap";

const nodeTypes: NodeTypes = {
  gateCluster: GateClusterNode,
  runtimeNode: RuntimeNodeCard,
};
const edgeTypes: EdgeTypes = { runtimeEdge: RuntimeEdge };

/** Group flat nodes by gateId for canvas layout. */
function groupByGate(
  nodes: UnifiedRuntimeNode[],
) {
  const map = new Map<string, UnifiedRuntimeNode[]>();
  for (const n of nodes) {
    const gid = n.gateId ?? "ungated";
    const arr = map.get(gid) ?? [];
    arr.push(n);
    map.set(gid, arr);
  }
  return map;
}

/** Compute a simple grid layout for gate clusters. */
function computeLayout(
  gateNodes: Map<string, UnifiedRuntimeNode[]>,
) {
  const GATE_W = 320;
  const GATE_H = 200;
  const GAP_X = 20;
  const GAP_Y = 20;
  const gates = Array.from(gateNodes.entries());
  const cols = Math.max(1, Math.ceil(Math.sqrt(gates.length)));
  const positions: Record<string, { x: number; y: number }> = {};
  gates.forEach(([gid], i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions[gid] = {
      x: col * (GATE_W + GAP_X),
      y: row * (GATE_H + GAP_Y),
    };
  });
  return { gates: positions, gateNodes };
}

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
  const [dir, setDir] = useState<"LR" | "TD">(
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("dir") === "TD" ? "TD" : "LR",
  );
  const [form, setForm] = useState<"stack" | "grid">(
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("form") === "stack" ? "stack" : "grid",
  );
  const [group, setGroup] = useState(true);

  const gateNodes = useMemo(() => groupByGate(model.nodes), [model.nodes]);
  const layout = useMemo(() => computeLayout(gateNodes), [gateNodes]);

  // Build React Flow nodes: gate boxes first, then node cards.
  const rfNodes: RFNode[] = useMemo(() => {
    const out: RFNode[] = [];
    const pos = layout.gates;

    for (const [gid, nodes] of layout.gateNodes) {
      const p = pos[gid] ?? { x: 0, y: 0 };
      const gateLabel = GATE_CHAIN.includes(gid as typeof GATE_CHAIN[number])
        ? `${gid.replace(/_/g, " ")}`
        : gid;
      out.push({
        id: `gate-${gid}`,
        type: "gateCluster",
        position: { x: p.x, y: p.y },
        data: {
          gateId: gid,
          gateLabel,
          gateSummary: "",
          boundary: "",
          headerH: 48,
          nodeCount: nodes.length,
          artifactCount: nodes.reduce((a, n) => a + n.artifacts.length, 0),
          state: "future" as const,
        },
        draggable: false,
        selectable: false,
        zIndex: 0,
        style: {
          width: 320,
          height: 200,
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: 12,
        },
      });

      nodes.forEach((n) => {
        const isActive = cursor >= 0 && model.orderedSteps[cursor]?.nodeId === n.id;
        out.push({
          id: n.id,
          type: "runtimeNode",
          position: { x: p.x + 16, y: p.y + 56 + (nodes.indexOf(n) % 5) * 28 },
          data: {
            node: {
              id: n.id,
              gate_id: n.gateId as "G0_CONTEXT" | "G1_ALIGNMENT" | "G2_EXECUTION" | "G3_PR" | "G4_MERGE" | "G5_DEPLOY" | "G6_PRODUCTION" | null,
              title: n.title,
              family: n.family ?? undefined,
              type: n.nodeType ?? undefined,
              boundary: n.authorityBoundary ?? undefined,
              purpose: n.purpose ?? undefined,
              fileReads: n.fileReads,
              fileWrites: n.fileWrites,
              artifacts: n.artifacts,
              runbook: n.runbook,
              taskControllerHistory: n.taskControllerHistory as string[],
              executorHistory: n.executorHistory as string[],
              checkpoints: n.checkpoints as string[],
              x: 0,
              y: 0,
              w: 0,
              h: 0,
            },
            state: isActive ? ("active" as const) : ("future" as const),
            active: isActive,
            selected: selection.kind === "node" && selection.id === n.id,
            boundary: n.authorityBoundary ?? "",
            onOpen: (path: string, kind: string) => onOpenArtifact(path, kind),
          },
          draggable: false,
          selectable: true,
          zIndex: 2,
        });
      });
    }
    return out;
  }, [layout, cursor, selection, model.orderedSteps, onOpenArtifact]);

  // Build edges from unified model edges.
  const rfEdges: RFEdge[] = useMemo(() => {
    return model.edges.map((e): RFEdge => {
      const isActive =
        e.kind === "ROUTE" &&
        cursor >= 0 &&
        model.orderedSteps[cursor]?.nodeId === e.source;
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
  }, [model.edges, cursor, model.orderedSteps]);

  const activeNodeId =
    cursor >= 0 ? model.orderedSteps[cursor]?.nodeId ?? null : null;

  // Follow cursor: center viewport on the active node.
  const programmaticMove = useRef(false);
  const prevActive = useRef<string | null>(null);
  useEffect(() => {
    if (!followCursor) return;
    if (prevActive.current === activeNodeId) return;
    prevActive.current = activeNodeId;
    const node = rfNodes.find((n) => n.id === activeNodeId);
    if (node) {
      programmaticMove.current = true;
      rf.setCenter(node.position.x + 100, node.position.y + 60, { zoom: 0.8, duration: 400 });
      const t = setTimeout(() => { programmaticMove.current = false; }, 480);
      return () => clearTimeout(t);
    }
  }, [followCursor, activeNodeId, rfNodes, rf]);

  const onCenterGate = (gateId: string) => {
    const g = layout.gates[gateId];
    if (g) rf.setCenter(g.x + 160, g.y + 100, { zoom: 0.7, duration: 400 });
  };

  return (
    <div className="dwo-canvas-wrap" data-testid="runtime-graph-canvas">
      <div className="dwo-layout-bar">
        <span className="dwo-layout-label">Layout</span>
        <button
          data-testid="layout-lr"
          className={dir === "LR" ? "on" : ""}
          onClick={() => setDir("LR")}
        >LR</button>
        <button
          data-testid="layout-td"
          className={dir === "TD" ? "on" : ""}
          onClick={() => setDir("TD")}
        >TD</button>
        <span className="dwo-layout-sep" />
        <button
          data-testid="layout-stack"
          className={form === "stack" ? "on" : ""}
          onClick={() => setForm("stack")}
        >Stack</button>
        <button
          data-testid="layout-grid"
          className={form === "grid" ? "on" : ""}
          onClick={() => setForm("grid")}
        >Grid</button>
        <span className="dwo-layout-sep" />
        <button
          data-testid="layout-group"
          className={group ? "on" : ""}
          onClick={() => setGroup((v) => !v)}
        >Group</button>
      </div>

      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.15}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, n) => {
          if (n.type === "runtimeNode") onSelectNode(n.id);
        }}
        onMoveStart={(_, viewport) => {
          if (!viewport) return;
          if (programmaticMove.current === false) onUserViewportInteract();
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