"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import type {
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
} from "@/lib/runtime/unifiedRuntime";
import {
  unknownQualificationProjection,
  type QualificationProjection,
} from "@/lib/dwo/qualificationProjection";

import WorkspaceHeader from "./WorkspaceHeader";
import RunStatusAxes from "./RunStatusAxes";
import ScenarioRunRail from "./ScenarioRunRail";
import RunHierarchy from "./RunHierarchy";
import RuntimeGraphCanvas from "./RuntimeGraphCanvas";
import NodeInspector from "./NodeInspector";
import NextFlowPanel from "./NextFlowPanel";
import RuntimePlayer from "./RuntimePlayer";

type InspectorTab =
  | "overview"
  | "files"
  | "artifacts"
  | "runbook"
  | "history"
  | "checkpoints"
  | "raw";

export default function UnifiedRunWorkspace({
  model,
  qualificationProjection,
  replayCursor,
  replayMode,
  replayTotal,
  onReplayCursorChange,
  onReplayModeChange,
}: {
  model: UnifiedRunWorkspaceModel;
  qualificationProjection?: QualificationProjection;
  replayCursor?: number;
  replayMode?: "LIVE" | "REPLAY";
  replayTotal?: number;
  onReplayCursorChange?: (cursor: number) => void;
  onReplayModeChange?: (mode: "LIVE" | "REPLAY") => void;
}) {
  const [mode, setMode] = useState<WorkspaceMode>(model.mode);
  const qualification =
    qualificationProjection ??
    unknownQualificationProjection(model.runId, "QUALIFICATION_READ_UNCONFIGURED");
  const projectionSync = model.projectionSyncState ?? (
    model.mode === "SIMULATED"
      ? "GAP"
      : model.canonicalHistoryAvailable
        ? "LIVE"
        : model.projectionStatus === "PROJECTION_UNAVAILABLE"
          ? "DEGRADED"
          : "GAP"
  );
  const [cursor, setCursor] = useState(replayCursor ?? 0);
  const [followCursor, setFollowCursor] = useState(true);
  const [selection, setSelection] = useState<{
    kind: "run" | "gate" | "node";
    id: string;
  }>({ kind: "node", id: model.orderedSteps[0]?.nodeId ?? model.nodes[0]?.id ?? model.runId });
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");
  const [playerSpeed, setPlayerSpeed] = useState(750);
  const [playing, setPlaying] = useState(false);

  const controlled = replayCursor !== undefined;
  const len = replayTotal ?? model.orderedSteps.length;
  const effectiveCursor = replayCursor ?? cursor;
  const replayPosition = useRef(effectiveCursor);
  const replayMove = useRef(onReplayCursorChange);
  replayPosition.current = effectiveCursor;
  replayMove.current = onReplayCursorChange;
  const currentStep = model.orderedSteps[Math.max(0, effectiveCursor - 1)];
  const currentNodeId = currentStep?.nodeId ?? null;

  const observedNodeIds = new Set(model.orderedSteps.map((step) => step.nodeId));
  const selectedNode = controlled
    ? model.nodes.find((n) => n.id === selection.id && observedNodeIds.has(n.id)) ?? null
    : model.nodes.find((n) => n.id === selection.id) ?? model.nodes.find((n) => n.id === currentNodeId) ?? null;

  const label = useMemo(() => {
    if (!selectedNode) return model.runId;
    return `${selectedNode.gateId ?? ""} · ${selectedNode.title}`;
  }, [selectedNode, model.runId]);

  // Auto-advance for LIVE_SIM mode.
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPlay = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setPlaying(false);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const play = useCallback(() => {
    if (timerRef.current) {
      stopPlay();
      return;
    }
    setPlaying(true);
    timerRef.current = setInterval(() => {
      if (controlled) {
        if (replayPosition.current >= len) { stopPlay(); return; }
        replayMove.current?.(Math.min(len, replayPosition.current + 1));
        return;
      }
      setCursor((c) => {
        if (c >= len - 1) {
          stopPlay();
          return c;
        }
        return c + 1;
      });
    }, playerSpeed);
  }, [len, playerSpeed, stopPlay, controlled]);

  const goTo = useCallback(
    (c: number) => {
      stopPlay();
      const clamped = Math.max(0, Math.min(controlled ? len : len - 1, c));
      if (controlled) { onReplayCursorChange?.(clamped); return; }
      setCursor(clamped);
      const step = model.orderedSteps[clamped];
      if (step) {
        setSelection({ kind: "node", id: step.nodeId });
      }
    },
    [len, model.orderedSteps, stopPlay, controlled, onReplayCursorChange],
  );

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelection({ kind: "node", id: nodeId });
    const ix = model.orderedSteps.findIndex((s) => s.nodeId === nodeId);
    if (!controlled && ix >= 0) setCursor(ix);
  }, [model.orderedSteps, controlled]);

  const handleOpenArtifact = useCallback((path: string, kind: string) => {
    // Open artifact — delegate to inspector's click handler or modal
    console.log(`[UnifiedRunWorkspace] open artifact: ${kind} ${path}`);
  }, []);

  const handleUserViewportInteract = useCallback(() => {
    setFollowCursor(false);
  }, []);

  const handleModeChange = useCallback((m: WorkspaceMode) => {
    if (controlled) { stopPlay(); onReplayModeChange?.(m === "LIVE" ? "LIVE" : "REPLAY"); return; }
    setMode(m);
    setCursor(0);
    if (m === "LIVE") {
      setPlaying(true);
    } else {
      stopPlay();
    }
  }, [stopPlay, controlled, onReplayModeChange]);

  return (
    <div className="dwo-workspace" data-testid="unified-run-workspace">
      <WorkspaceHeader model={model} mode={replayMode ?? mode} onModeChange={handleModeChange} />
      <RunStatusAxes
        projectionSync={projectionSync}
        view={(replayMode ?? mode) === "REPLAY" ? "REPLAY" : "CURRENT"}
        qualification={qualification}
      />
      <ScenarioRunRail model={model} selectedRunId={model.runId} onSelectRun={() => {}} />

      <div className="dwo-workspace-body">
        <aside className="dwo-workspace-left" data-testid="workspace-left">
          <RunHierarchy model={model} selectedId={selection.id} onSelect={handleSelectNode} />
          <NextFlowPanel model={model} />
        </aside>

        <main className="dwo-workspace-center" data-testid="workspace-center">
          <ReactFlowProvider>
            <RuntimeGraphCanvas
              model={model}
              cursor={effectiveCursor}
              selection={selection}
              followCursor={followCursor}
              onSelectNode={handleSelectNode}
              onOpenArtifact={handleOpenArtifact}
              onUserViewportInteract={handleUserViewportInteract}
            />
          </ReactFlowProvider>
          <RuntimePlayer
            cursorIsPrefix={controlled}
            cursor={effectiveCursor}
            len={len}
            mode={replayMode ?? mode}
            speed={playerSpeed}
            playing={playing}
            label={label}
            onFirst={() => goTo(0)}
            onPrev={() => goTo(effectiveCursor - 1)}
            onToggle={play}
            onNext={() => goTo(effectiveCursor + 1)}
            onLast={() => goTo(controlled ? len : len - 1)}
            onScrub={goTo}
            onMode={handleModeChange}
            onSpeed={setPlayerSpeed}
          />
        </main>

        <aside className="dwo-workspace-right" data-testid="workspace-right">
          <NodeInspector
            node={selectedNode}
            activeTab={inspectorTab}
            onTabChange={setInspectorTab}
          />
        </aside>
      </div>
    </div>
  );
}