// Fixture Lab — client shell.
//
// This component is deliberately thin: it owns ONLY the selection state. Every
// scenario model it renders was already materialized ON THE SERVER, where the
// DWO-UR-30-V1 evidence pack is readable.
//
// Do NOT import materializeFixtureScenario here. The browser bundle cannot
// resolve `fs`, so a client-side materialization would silently drop all
// evidence and render an empty projection (fail-OPEN).

"use client";

import { useState } from "react";

import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import { DEV_RUN_020, FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

export interface FixtureLabProps {
  catalog: typeof FIXTURE_CATALOG;
  /** Pre-materialized models, keyed by catalog id. Built on the server. */
  models: Record<string, UnifiedRunWorkspaceModel>;
  defaultId: string;
}

export default function FixtureLabClient({
  catalog,
  models,
  defaultId,
}: FixtureLabProps) {
  const [selectedId, setSelectedId] = useState(defaultId);

  const model = models[selectedId];
  const isConflict = selectedId === DEV_RUN_020;

  // Fail-closed: a missing pre-materialized model must never render as an
  // empty-but-valid workspace.
  if (!model) {
    return (
      <div className="dwo-fixture-lab" data-testid="fixture-unavailable">
        <p className="dwo-fixture-label">
          Fixture data — development/review surface only. Not reachable from
          production run routes.
        </p>
        <div className="dwo-fixture-conflict" role="alert">
          {selectedId}: materialization UNAVAILABLE — the DWO-UR-30-V1 evidence
          pack could not be read on the server. No projection is shown rather
          than an empty one.
        </div>
      </div>
    );
  }

  return (
    <div className="dwo-fixture-lab">
      <p className="dwo-fixture-label">
        Fixture data — development/review surface only. Not reachable from production run routes.
      </p>

      <nav className="dwo-fixture-rail" data-testid="fixture-catalog">
        {catalog.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`dwo-fixture-btn ${selectedId === f.id ? "dwo-fixture-btn-selected" : ""}`}
            onClick={() => setSelectedId(f.id)}
          >
            <span>{f.id}</span>
            <span className="dwo-fixture-kind">{f.kind}</span>
          </button>
        ))}
      </nav>

      {isConflict && (
        <div className="dwo-fixture-conflict" data-testid="conflict-banner">
        DEV-RUN-020: runState=INCOMPATIBLE sourceProfile=UNKNOWN syncState=UNAVAILABLE —
        fail-closed. Zero nodes, zero edges.
      </div>
      )}

      <UnifiedRunWorkspace model={model} />
    </div>
  );
}