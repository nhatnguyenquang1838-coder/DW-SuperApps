"use client";

import { useState } from "react";
import { FIXTURE_CATALOG, DEV_RUN_020 } from "@/lib/dwo/fixtureSpec";
import { materializeFixtureScenario } from "@/lib/dwo/materializeFixtureScenario";
import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

export default function DevFixturesPage() {
  const [selectedId, setSelectedId] = useState("DEV-RUN-001");
  const selectedEntry = FIXTURE_CATALOG.find((f) => f.id === selectedId)!;
  const model: UnifiedRunWorkspaceModel = materializeFixtureScenario(selectedEntry);
  const isConflict = selectedId === DEV_RUN_020;

  return (
    <div className="dwo-fixture-lab">
      <p className="dwo-fixture-label">
        Fixture data — development/review surface only. Not reachable from production run routes.
      </p>

      <nav className="dwo-fixture-rail" data-testid="fixture-catalog">
        {FIXTURE_CATALOG.map((f) => (
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
          DEV-RUN-020: incompatible-source negative — fail-closed. Zero nodes, zero edges.
        </div>
      )}

      <UnifiedRunWorkspace model={model} />
    </div>
  );
}