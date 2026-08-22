"use client";

import { useEffect, useState } from "react";
import type { RunHierarchy, HierarchyNode } from "@/lib/observatory";

// M5 — animated, hierarchical run-flow. Each step/gate/node/issue is a card,
// connected by explicit connectors (recorded relationships, never inferred).
// Cards animate into view in sequence; the "active" card (last open/correction)
// pulses gently. No new dependency — pure CSS keyframes (see globals.css).
//
// Content is source-backed: every node/edge comes from the RunHierarchy model
// (built from the mock fixture / recorded gates+nodes), not from a hardcoded
// layout in this component.

type Props = {
  hierarchy: RunHierarchy;
  // id of the card that should be highlighted as active/pulsing
  activeId?: string;
  // id of the root card (rendered distinctly)
};

const KIND_STYLES: Record<HierarchyNode["kind"], string> = {
  root: "border-accent/70 bg-accent/10",
  gate: "border-amber-400/60 bg-amber-400/5",
  node: "border-edge bg-panel",
  issue: "border-fuchsia-400/60 bg-fuchsia-400/5",
};

const KIND_BADGE: Record<HierarchyNode["kind"], string> = {
  root: "ROOT",
  gate: "GATE",
  node: "NODE",
  issue: "ISSUE",
};

export default function AnimatedRunFlow({ hierarchy, activeId }: Props) {
  const [revealed, setRevealed] = useState(0);

  // Reveal cards one-by-one (sequential animation).
  useEffect(() => {
    setRevealed(0);
    const total = hierarchy.nodes.length;
    let i = 0;
    const t = setInterval(() => {
      i += 1;
      setRevealed(i);
      if (i >= total) clearInterval(t);
    }, 220);
    return () => clearInterval(t);
  }, [hierarchy.nodes.length]);

  // Build a quick lookup: from -> [labels] for connectors pointing to each node.
  const incoming = (id: string) =>
    hierarchy.connectors
      .filter((c) => c.to === id)
      .map((c) => ({ from: c.from, label: c.label }));

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <h2 className="mb-1 text-base font-semibold">Hierarchical run flow</h2>
      <p className="mb-4 text-xs text-muted">
        Source-backed steps. Each card is a recorded node/gate/issue; connectors
        are explicit (recorded), never inferred. Cards animate in sequence.
      </p>

      <ol className="relative space-y-0">
        {hierarchy.nodes.map((n, idx) => {
          const isRevealed = idx < revealed;
          const isActive = activeId === n.id;
          const connectors = incoming(n.id);
          return (
            <li
              key={`${n.id}-${idx}`}
              className={`runflow-card relative pl-8 ${isRevealed ? "is-visible" : ""} ${
                isActive ? "runflow-active" : ""
              }`}
            >
              {/* connector line from previous card */}
              {idx > 0 && (
                <span
                  className="runflow-connector"
                  aria-hidden="true"
                />
              )}
              {/* node marker */}
              <span className="runflow-dot" aria-hidden="true" />

              <div
                className={`rounded-lg border p-3 ${KIND_STYLES[n.kind]} ${
                  isActive ? "runflow-active-card" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                      {KIND_BADGE[n.kind]}
                    </span>
                    <span className="font-semibold">{n.id}</span>
                  </div>
                  <span className="text-xs text-muted">{n.label}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 text-xs">
                  <span className="text-muted">
                    status: <span className="code">{n.status}</span>
                  </span>
                  {n.detail && (
                    <span className="text-muted">· {n.detail}</span>
                  )}
                </div>
                {/* explicit incoming connectors (recorded) */}
                {connectors.length > 0 && (
                  <div className="mt-2 space-y-0.5 border-t border-edge/40 pt-2 text-[11px] text-muted">
                    {connectors.map((c, ci) => (
                      <div key={ci}>
                        <span className="code text-accent">{c.from}</span>
                        <span className="mx-1 text-muted">→</span>
                        <span>{c.label}</span>
                      </div>
                    ))}
                  </div>
                )}
                {!n.sourceBacked && (
                  <p className="mt-1 text-[11px] text-amber-400/80">
                    not recorded in source
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {hierarchy.nodes.length === 0 && (
        <p className="text-sm text-muted">No recorded hierarchy in this source.</p>
      )}
    </div>
  );
}
