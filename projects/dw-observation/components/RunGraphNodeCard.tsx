"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { HierarchyNode } from "@/lib/observatory";

export type GraphNodeData = {
  node: HierarchyNode;
  active: boolean;
  [key: string]: unknown;
};

const KIND_LABEL: Record<HierarchyNode["kind"], string> = {
  root: "ROOT",
  gate: "GATE",
  node: "NODE",
  issue: "ISSUE",
};

const KIND_RING: Record<HierarchyNode["kind"], string> = {
  root: "border-accent/70",
  gate: "border-amber-400/60",
  node: "border-edge",
  issue: "border-fuchsia-400/60",
};

function RunGraphNodeCardImpl({ data }: NodeProps) {
  const { node, active } = data as GraphNodeData;
  return (
    <div
      data-testid="runflow-node"
      data-node-id={node.id}
      data-node-kind={node.kind}
      data-active={active ? "true" : "false"}
      className={`runflow-graph-node w-52 rounded-lg border bg-panel p-3 ${
        KIND_RING[node.kind]
      } ${active ? "runflow-graph-active" : ""}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      <div className="flex items-center justify-between">
        <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
          {KIND_LABEL[node.kind]}
        </span>
        <span className="font-semibold">{node.id}</span>
      </div>
      <div className="mt-1 text-xs text-muted">{node.label}</div>
      <div className="mt-1 text-[11px]">
        <span className="text-muted">status: </span>
        <span className="code">{node.status}</span>
      </div>
      {node.detail && (
        <div className="mt-0.5 text-[11px] text-muted">· {node.detail}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
    </div>
  );
}

export default memo(RunGraphNodeCardImpl);
