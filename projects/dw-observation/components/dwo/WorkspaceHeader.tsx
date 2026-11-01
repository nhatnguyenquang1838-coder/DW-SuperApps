"use client";

import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";
import styles from "./WorkspaceHeader.module.css";

const modeCopy: Record<WorkspaceMode, string> = {
  LIVE: "Read-only durable source view; this does not grant production authority.",
  REPLAY: "Read-only view of a selected historical position.",
  SIMULATED: "Read-only fixture preview; it does not represent live production state or grant production authority.",
};

const modeLabel: Record<WorkspaceMode, string> = {
  LIVE: "Live source",
  REPLAY: "Replay",
  SIMULATED: "Fixture preview",
};

export default function WorkspaceHeader({
  model,
  mode,
  onModeChange,
}: {
  model: UnifiedRunWorkspaceModel;
  mode: WorkspaceMode;
  onModeChange: (m: WorkspaceMode) => void;
}) {
  const fixturePreview = model.mode === "SIMULATED";
  const currentLabel = fixturePreview ? "Current fixture state" : modeLabel.LIVE;
  const description = fixturePreview
    ? mode === "REPLAY"
      ? "Read-only fixture replay; it does not represent live production state or grant production authority."
      : modeCopy.SIMULATED
    : modeCopy[mode];
  return (
    <header className={`dwo-ws-header ${styles.header}`} data-testid="workspace-header">
      <div className="dwo-ws-header-left">
        <h1 className="dwo-ws-title">{model.runId}</h1>
        <span className="dwo-ws-badge" data-mode={mode}>{mode === "LIVE" ? currentLabel : modeLabel[mode]}</span>
        <span className="dwo-ws-status">{model.status}</span>
      </div>
      <div className={`dwo-ws-header-right ${styles.controls}`}>
        <label className={styles.modeControl}>
          <span className={styles.modeLabel}>Data mode</span>
          <select
            value={mode}
            onChange={(e) => onModeChange(e.target.value as WorkspaceMode)}
            data-testid="workspace-mode-select"
            aria-label="Workspace mode"
          >
            <option value="LIVE">{currentLabel}</option>
            <option value="REPLAY">Replay</option>
            <option value="SIMULATED">Fixture preview</option>
          </select>
        </label>
        <p className={styles.modeExplanation} data-testid="workspace-mode-explanation" aria-live="polite">{description}</p>
      </div>
    </header>
  );
}