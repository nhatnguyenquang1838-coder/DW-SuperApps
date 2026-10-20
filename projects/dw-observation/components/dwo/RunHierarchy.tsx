"use client";

import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

/**
 * RunHierarchy — the hierarchy tree region.
 *
 * Distinct from the dependency graph (spec: hierarchy != dependency).
 * Renders the model.hierarchy when available; otherwise shows
 * explicit UNAVAILABLE state (fail-closed).
 */
export default function RunHierarchy({ model }: { model: UnifiedRunWorkspaceModel }) {
  const hierarchy = model.hierarchy as Record<string, unknown> | null;

  if (!hierarchy) {
    return (
      <div className="dwo-hierarchy" data-testid="run-hierarchy" data-state="unavailable">
        <h3 className="dwo-hierarchy-title">Hierarchy</h3>
        <span className="dwo-unknown">UNAVAILABLE</span>
      </div>
    );
  }

  return (
    <div className="dwo-hierarchy" data-testid="run-hierarchy" data-state="loaded">
      <h3 className="dwo-hierarchy-title">Hierarchy</h3>
      <pre className="dwo-hierarchy-raw" data-testid="hierarchy-tree">
        {JSON.stringify(hierarchy, null, 2)}
      </pre>
    </div>
  );
}