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

import type { LoginEpicRun, GateId, RuntimeNode, NodeState } from "@/lib/loginEpicRuntimeGraph";
import {
  getActiveRoute,
  getNodeState,
  getGateState,
  makeArtifactPreview,
  shouldDisableFollowOnMove,
} from "@/lib/loginEpicRuntimeGraph";
import { computeRunLayout, type DisplayDir, type DisplayForm } from "@/lib/loginEpicLayout";
import GateClusterNode from "./GateClusterNode";
import RuntimeNodeCard from "./RuntimeNodeCard";
import RuntimeEdge from "./RuntimeEdge";
import FamilyBandNode from "./FamilyBandNode";

const nodeTypes: NodeTypes = {
  gateCluster: GateClusterNode,
  runtimeNode: RuntimeNodeCard,
  familyBand: FamilyBandNode,
};
const edgeTypes: EdgeTypes = { runtimeEdge: RuntimeEdge };

export default function RuntimeGraphCanvas({
  run,
  cursor,
  selection,
  followCursor,
  onSelectNode,
  onOpenArtifact,
  onUserViewportInteract,
}: {
  run: LoginEpicRun;
  cursor: number;
  selection: { kind: "run" | "gate" | "node"; id: string };
  followCursor: boolean;
  onSelectNode: (nodeId: string) => void;
  onOpenArtifact: (path: string, kind: string) => void;
  onUserViewportInteract: () => void;
}) {
  const rf = useReactFlow();
  const [dir, setDir] = useState<DisplayDir>(
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("dir") === "TD" ? "TD" : "LR",
  );
  const [form, setForm] = useState<DisplayForm>(
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("form") === "stack" ? "stack" : "grid",
  );
  const [group, setGroup] = useState<boolean>(
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("group") !== "0" : true,
  );

  const layout = useMemo(
    () => computeRunLayout(run, { dir, form, group }),
    [run, dir, form, group],
  );

  // Build React Flow nodes: gate boxes first (background), then family bands, then node cards.
  const rfNodes: RFNode[] = useMemo(() => {
    const out: RFNode[] = [];
    // gate background boxes
    layout.gates.forEach((g) => {
      const state = getGateState(run, g.id, cursor);
      out.push({
        id: `gate-${g.id}`,
        type: "gateCluster",
        position: { x: g.x, y: g.y },
        data: {
          gateId: g.id,
          gateLabel: run.gates.find((x) => x.id === g.id)?.label ?? g.id,
          gateSummary: run.gates.find((x) => x.id === g.id)?.summary ?? "",
          boundary: g.boundary,
          headerH: g.headerH,
          nodeCount: run.gates.find((x) => x.id === g.id)?.nodes.length ?? 0,
          artifactCount: run.gates.find((x) => x.id === g.id)?.gateArtifacts.length ?? 0,
          state,
        },
        draggable: false,
        selectable: false,
        zIndex: 0,
        style: {
          width: g.w,
          height: g.h,
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: 12,
        },
      });
      // family group bands
      g.families.forEach((f) => {
        out.push({
          id: `fam-${g.id}-${f.family}`,
          type: "familyBand",
          position: { x: f.x, y: f.y },
          data: { family: f.family, boundary: g.boundary },
          draggable: false,
          selectable: false,
          zIndex: 1,
          style: { width: f.w, height: f.h },
        } as RFNode);
      });
    });
    // node cards
    layout.nodes.forEach((ln) => {
      const n = run.gates.flatMap((g) => g.nodes).find((x) => x.id === ln.id) as RuntimeNode;
      const state: NodeState = getNodeState(run, n.id, cursor);
      out.push({
        id: n.id,
        type: "runtimeNode",
        position: { x: ln.x, y: ln.y },
        data: {
          node: n,
          state,
          active: state === "active",
          selected: selection.kind === "node" && selection.id === n.id,
          boundary: n.boundary,
          onOpen: (path: string, kind: string) => onOpenArtifact(path, kind),
        },
        draggable: false,
        selectable: true,
        zIndex: 2,
      });
    });
    return out;
  }, [layout, run, cursor, selection]);

  // Build edges: route spine + fanout, with active highlight.
  const rfEdges: RFEdge[] = useMemo(() => {
    const active = getActiveRoute(run, cursor);
    const routeIds = new Set(run.route.map((r) => r.node_id));
    return layout.edges.map((e): RFEdge => {
      const isRoute = e.kind === "route";
      const isActive = isRoute && routeIds.has(active.node_id)
        ? e.source === run.route[cursor]?.node_id && e.target === run.route[cursor + 1]?.node_id
        : false;
      // simpler active: connect cursor node to next
      const activeRoute = isRoute && e.source === active.node_id;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: "runtimeEdge",
        animated: false,
        zIndex: 0,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: {
          stroke: e.kind === "fanout" ? "rgba(140,147,166,0.25)" : isRoute ? "#8a93a6" : "#6ca9ff",
          strokeWidth: e.kind === "fanout" ? 1 : 1.5,
          strokeDasharray: e.kind === "fanout" ? "3 4" : undefined,
        },
        data: { kind: e.kind, active: activeRoute },
        className: activeRoute ? "runtime-active-edge" : "",
      } as RFEdge;
    });
  }, [layout, run, cursor]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = getActiveRoute(run, cursor);
  const activeGateId: GateId | null = active ? active.gate_id : null;

  // Follow cursor: center viewport on the active node.
  const programmaticMove = useRef(false);
  const prevActive = useRef<string | null>(null);
  useEffect(() => {
    if (!followCursor) return;
    const activeNodeId = active.node_id;
    if (prevActive.current === activeNodeId) return;
    prevActive.current = activeNodeId;
    const node = rfNodes.find((n) => n.id === activeNodeId);
    if (node) {
      programmaticMove.current = true;
      rf.setCenter(node.position.x + 100, node.position.y + 60, { zoom: 0.8, duration: 400 });
      const t = setTimeout(() => {
        programmaticMove.current = false;
      }, 480);
      return () => clearTimeout(t);
    }
  }, [followCursor, active.node_id, rfNodes, rf]); // eslint-disable-line react-hooks/exhaustive-deps

  const onCenterGate = (gateId: GateId) => {
    const g = layout.gates.find((x) => x.id === gateId);
    if (g) rf.setCenter(g.x + g.w / 2, g.y + g.h / 2, { zoom: 0.7, duration: 400 });
  };

  return (
    <div className="leg-canvas-wrap" data-testid="runtime-graph-canvas">
      <div className="leg-layout-bar">
        <span className="leg-layout-label">Layout</span>
        <button data-testid="layout-lr" className={dir === "LR" ? "on" : ""} onClick={() => setDir("LR")}>LR</button>
        <button data-testid="layout-td" className={dir === "TD" ? "on" : ""} onClick={() => setDir("TD")}>TD</button>
        <span className="leg-layout-sep" />
        <button data-testid="layout-stack" className={form === "stack" ? "on" : ""} onClick={() => setForm("stack")}>Stack</button>
        <button data-testid="layout-grid" className={form === "grid" ? "on" : ""} onClick={() => setForm("grid")}>Grid</button>
        <span className="leg-layout-sep" />
        <button data-testid="layout-group" className={group ? "on" : ""} onClick={() => setGroup((v) => !v)}>Group</button>
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
          if (shouldDisableFollowOnMove(programmaticMove.current)) onUserViewportInteract();
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

import MiniMap from "./MiniMap";
function MiniMapWrapper(props: {
  run: LoginEpicRun;
  activeGateId: GateId | null;
  onCenterGate: (g: GateId) => void;
}) {
  return <MiniMap {...props} />;
}

export { makeArtifactPreview };
