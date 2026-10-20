"use client";

import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

export default function ScenarioRunRail({
  model,
  selectedRunId,
  onSelectRun,
}: {
  model: UnifiedRunWorkspaceModel;
  selectedRunId: string;
  onSelectRun: (runId: string) => void;
}) {
  // The rail shows the current run context; in a full implementation this
  // would list available runs. For now it displays the active run's
  // task reference and scenario metadata.
  return (
    <nav className="dwo-scenario-rail" data-testid="scenario-run-rail">
      <span className="dwo-rail-run-id">{model.runId}</span>
      {model.taskRef && (
        <span className="dwo-rail-taskref">{model.taskRef}</span>
      )}
      <span className="dwo-rail-source">{model.sourceDigest ?? "UNKNOWN"}</span>
    </nav>
  );
}