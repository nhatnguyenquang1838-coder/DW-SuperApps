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
import FixtureReplayControls from "@/components/dwo/FixtureReplayControls";
import { DEV_RUN_020, FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";
import type { ProjectionEvent } from "@/lib/live";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";
import { ReplaySession } from "@/lib/replay";
import { projectFixtureReplayView } from "@/lib/dwo/fixtureReplayView";

export interface FixtureLabProps {
  catalog: typeof FIXTURE_CATALOG;
  /** Pre-materialized models, keyed by catalog id. Built on the server. */
  models: Record<string, UnifiedRunWorkspaceModel>;
  /** Ordinal-ordered event streams for each model's explicit subtree. */
  replayEvents: Record<string, ProjectionEvent[]>;
  defaultId: string;
}

export default function FixtureLabClient({
  catalog,
  models,
  replayEvents,
  defaultId,
}: FixtureLabProps) {
  const [selectedId, setSelectedId] = useState(defaultId);
  const [session, setSession] = useState(() => new ReplaySession([]));
  const [resetEpoch, setResetEpoch] = useState(0);
  const [, refresh] = useState(0);

  const model = models[selectedId];
  const events = replayEvents[selectedId] ?? [];
  const frame = session.frame();
  const viewModel = model ? projectFixtureReplayView(model, frame.projection.events) : undefined;
  const isConflict = selectedId === DEV_RUN_020;

  // Fail-closed: a missing pre-materialized model must never render as an
  // empty-but-valid workspace.
  if (!model) {
    return (
      <div className="dwo-fixture-lab" data-testid="fixture-unavailable">
        <div
          className="mb-4 inline-flex items-center gap-2 rounded border px-3 py-1.5"
          style={{ borderColor: 'var(--dwo-color-state-amber)', background: 'var(--dwo-color-bg-subtle)' }}
          data-testid="dev-fixture-indicator"
        >
          <strong className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--dwo-color-state-amber)' }}>DEV FIXTURE</strong>
          <span className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>read-only preview · not reachable from production routes</span>
        </div>
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
      <div data-testid="dev-fixture-indicator" className="mb-4 inline-flex items-center gap-2 rounded border px-3 py-1.5" style={{ borderColor: 'var(--dwo-color-state-amber)', background: 'var(--dwo-color-bg-subtle)' }}>
        <strong className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--dwo-color-state-amber)' }}>DEV FIXTURE</strong>
        <span className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>read-only preview · not reachable from production routes</span>
      </div>

      <nav className="dwo-fixture-rail" data-testid="fixture-catalog">
        {catalog.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`dwo-fixture-btn ${selectedId === f.id ? "dwo-fixture-btn-selected" : ""}`}
            onClick={() => { setSelectedId(f.id); setSession(new ReplaySession([])); }}
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

      <UnifiedRunWorkspace key={`workspace-${selectedId}-${resetEpoch}`} model={viewModel!} replayCursor={frame.cursor} replayTotal={frame.total} replayMode={session.mode}
        onReplayCursorChange={(cursor) => { session.rewindTo(cursor); refresh((value) => value + 1); }}
        onReplayModeChange={(mode) => { if (mode === "LIVE") session.resumeLive(); else session.enterReplay(); refresh((value) => value + 1); }} />
      <FixtureReplayControls
        key={`controls-${selectedId}`}
        runId={selectedId}
        events={events}
        session={session}
        onChange={() => refresh((value) => value + 1)}
        onReset={() => { setSession(new ReplaySession([])); setResetEpoch(value => value + 1); }}
      />
    </div>
  );
}