"use client";

import { useState, useMemo, useCallback } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import type {
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
} from "@/lib/runtime/unifiedRuntime";

import WorkspaceHeader from "./WorkspaceHeader";
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
}: {
  model: UnifiedRunWorkspaceModel;
}) {
  const [mode, setMode] = useState<WorkspaceMode>(model.mode);
  const [cursor, setCursor] = useState(0);
  const [followCursor, setFollowCursor] = useState(true);
  const [selection, setSelection] = useState<{
    kind: "run" | "gate" | "node";
    id: string;
  }>({ kind: "run", id: model.runId });
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");
  const [playerSpeed, setPlayerSpeed] = useState(750);
  const [playing, setPlaying] = useState(false);

  const len = model.orderedSteps.length;
  const currentStep = model.orderedSteps[cursor];
  const currentNodeId = currentStep?.nodeId ?? null;

  const selectedNode = model.nodes.find((n) => n.id === currentNodeId) ?? null;

  const label = useMemo(() => {
    if (!selectedNode) return model.runId;
    return `${selectedNode.gateId ?? ""} · ${selectedNode.title}`;
  }, [selectedNode, model.runId]);

  // Auto-advance for LIVE_SIM mode
  const timerRef = useState<ReturnType<typeof setInterval> | null>(null);

  const stopPlay = useCallback(() => {
    if (timerRef[0]) {
      clearInterval(timerRef[0]);
      timerRef[0] = null;
    }
    setPlaying(false);
  }, [timerRef]);

  const play = useCallback(() => {
    if (timerRef[0]) {
      stopPlay();
      return;
    }
    setPlaying(true);
    timerRef[0] = setInterval(() => {
      setCursor((c) => {
        if (c >= len - 1) {
          stopPlay();
          return c;
        }
        return c + 1;
      });
    }, playerSpeed);
  }, [len, playerSpeed, stopPlay, timerRef]);

  const goTo = useCallback(
    (c: number) => {
      stopPlay();
      const clamped = Math.max(0, Math.min(len - 1, c));
      setCursor(clamped);
      const step = model.orderedSteps[clamped];
      if (step) {
        setSelection({ kind: "node", id: step.nodeId });
      }
    },
    [len, model.orderedSteps, stopPlay],
  );

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelection({ kind: "node", id: nodeId });
    const ix = model.orderedSteps.findIndex((s) => s.nodeId === nodeId);
    if (ix >= 0) setCursor(ix);
  }, [model.orderedSteps]);

  const handleOpenArtifact = useCallback((path: string, kind: string) => {
    // Open artifact — delegate to inspector's click handler or modal
    console.log(`[UnifiedRunWorkspace] open artifact: ${kind} ${path}`);
  }, []);

  const handleUserViewportInteract = useCallback(() => {
    setFollowCursor(false);
  }, []);

  const handleModeChange = useCallback((m: WorkspaceMode) => {
    setMode(m);
    setCursor(0);
    if (m === "LIVE") {
      setPlaying(true);
    } else {
      stopPlay();
    }
  }, [stopPlay]);

  return (
    <div className="dwo-workspace" data-testid="unified-run-workspace">
      <WorkspaceHeader model={model} mode={mode} onModeChange={handleModeChange} />
      <ScenarioRunRail model={model} selectedRunId={model.runId} onSelectRun={() => {}} />

      <div className="dwo-workspace-body">
        <aside className="dwo-workspace-left" data-testid="workspace-left">
          <RunHierarchy model={model} />
          <NextFlowPanel model={model} />
        </aside>

        <main className="dwo-workspace-center" data-testid="workspace-center">
          <ReactFlowProvider>
            <RuntimeGraphCanvas
              model={model}
              cursor={cursor}
              selection={selection}
              followCursor={followCursor}
              onSelectNode={handleSelectNode}
              onOpenArtifact={handleOpenArtifact}
              onUserViewportInteract={handleUserViewportInteract}
            />
          </ReactFlowProvider>
          <RuntimePlayer
            cursor={cursor}
            len={len}
            mode={mode}
            speed={playerSpeed}
            playing={playing}
            label={label}
            onFirst={() => goTo(0)}
            onPrev={() => goTo(cursor - 1)}
            onToggle={play}
            onNext={() => goTo(cursor + 1)}
            onLast={() => goTo(len - 1)}
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