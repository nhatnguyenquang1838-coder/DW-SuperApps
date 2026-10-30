"use client";

import { useState } from "react";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

type Tree = { id: string; parent: string | null; atomic: boolean; children: Tree[] };
function asTree(value: unknown, ancestors = new Set<object>(), ids = new Set<string>(), expectedParent: string | null = null): Tree | null {
  if (!value || typeof value !== "object") return null;
  if (ancestors.has(value)) return null;
  ancestors.add(value);
  const row = value as Record<string, unknown>;
  if (typeof row.id !== "string" || !row.id || ids.has(row.id) || !(row.parent === null || typeof row.parent === "string") || row.parent !== expectedParent || !Array.isArray(row.children)) return null;
  ids.add(row.id);
  const nodeId = row.id;
  const children = row.children.map((child) => asTree(child, new Set(ancestors), ids, nodeId));
  if (children.some((child) => child === null)) return null;
  return { id: nodeId, parent: row.parent, atomic: row.atomic === true, children: children as Tree[] };
}

function TreeBranch({ node, selectedId, onSelect, depth = 0 }: { node: Tree; selectedId: string; onSelect: (id: string) => void; depth?: number }) {
  const [expanded, setExpanded] = useState(true);
  return (
    <li role="treeitem" aria-expanded={node.children.length ? expanded : undefined} aria-selected={selectedId === node.id} aria-label={`${node.id}${node.atomic ? ", atomic" : ""}`}>
      <div className="dwo-hierarchy-row" style={{ paddingInlineStart: `${depth * 14}px` }}>
        {node.children.length > 0 && <button type="button" aria-label={`${expanded ? "Collapse" : "Expand"} ${node.id}`} onClick={() => setExpanded((value) => !value)}>{expanded ? "−" : "+"}</button>}
        <button type="button" data-testid={`hierarchy-select-${node.id}`} aria-current={selectedId === node.id ? "true" : undefined} onKeyDown={(event) => {
          const buttons = Array.from(event.currentTarget.closest('[role="tree"]')?.querySelectorAll<HTMLButtonElement>('button[data-testid^="hierarchy-select-"]') ?? []);
          const index = buttons.indexOf(event.currentTarget);
          const next = event.key === "ArrowDown" ? buttons[index + 1] : event.key === "ArrowUp" ? buttons[index - 1] : event.key === "Home" ? buttons[0] : event.key === "End" ? buttons.at(-1) : undefined;
          if (next) { event.preventDefault(); next.focus(); }
        }} onClick={() => onSelect(node.id)}>{node.id}{node.atomic && <span className="dwo-atomic-marker"> · Atomic</span>}</button>
      </div>
      {node.children.length > 0 && expanded && <ul role="group">{node.children.map((child) => <TreeBranch key={child.id} node={child} selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />)}</ul>}
    </li>
  );
}

export default function RunHierarchy({ model, selectedId = model.runId, onSelect = () => {} }: { model: UnifiedRunWorkspaceModel; selectedId?: string; onSelect?: (id: string) => void }) {
  const hierarchy = asTree(model.hierarchy);
  if (!hierarchy) return <div className="dwo-hierarchy" data-testid="run-hierarchy" data-state="unavailable"><h3 className="dwo-hierarchy-title">Hierarchy</h3><span className="dwo-unknown">UNAVAILABLE</span></div>;
  return <div className="dwo-hierarchy" data-testid="run-hierarchy" data-state="loaded"><h3 className="dwo-hierarchy-title">Hierarchy</h3><ul role="tree" aria-label="Run hierarchy" data-testid="hierarchy-tree"><TreeBranch node={hierarchy} selectedId={selectedId} onSelect={onSelect} /></ul></div>;
}
