"use client";

import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";

export default function WorkspaceHeader({
  model,
  mode,
  onModeChange,
}: {
  model: UnifiedRunWorkspaceModel;
  mode: WorkspaceMode;
  onModeChange: (m: WorkspaceMode) => void;
}) {
  return (
    <header className="dwo-ws-header" data-testid="workspace-header">
      <div className="dwo-ws-header-left">
        <h1 className="dwo-ws-title">{model.runId}</h1>
        <span className="dwo-ws-badge" data-mode={mode}>
          {mode}
        </span>
        <span className="dwo-ws-status">{model.status}</span>
      </div>
      <div className="dwo-ws-header-right">
        <select
          value={mode}
          onChange={(e) => onModeChange(e.target.value as WorkspaceMode)}
          data-testid="workspace-mode-select"
        >
          <option value="LIVE">LIVE</option>
          <option value="REPLAY">REPLAY</option>
          <option value="SIMULATED">SIMULATED</option>
        </select>
      </div>
    </header>
  );
}