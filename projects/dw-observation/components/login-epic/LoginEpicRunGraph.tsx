"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import type {
  LoginEpicRuntimeFixture,
  LoginEpicRun,
  ReplayMode,
} from "@/lib/loginEpicRuntimeGraph";
import { getRun, clampCursor, getActiveRoute, getRouteIndex, makeArtifactPreview } from "@/lib/loginEpicRuntimeGraph";
import EpicRunRail from "./EpicRunRail";
import RuntimeGraphCanvas from "./RuntimeGraphCanvas";
import RuntimePlayer from "./RuntimePlayer";
import RuntimeDetailsPanel from "./RuntimeDetailsPanel";
import ArtifactModal from "./ArtifactModal";

export default function LoginEpicRunGraph({ epic }: { epic: LoginEpicRuntimeFixture }) {
  const [selectedRunId, setSelectedRunId] = useState<string>(epic.runs[0].id);
  const run: LoginEpicRun = useMemo(() => getRun(epic, selectedRunId), [epic, selectedRunId]);
  const len = run.route.length;
  const [cursor, setCursor] = useState(0);
  const [mode, setMode] = useState<ReplayMode>("REPLAY");
  const [speed, setSpeed] = useState(750);
  const [playing, setPlaying] = useState(false);
  const [selection, setSelection] = useState<{ kind: "run" | "gate" | "node"; id: string }>({ kind: "run", id: epic.runs[0].id });
  const [detailTab, setDetailTab] = useState<string>("overview");
  const [modal, setModal] = useState<{ title: string; body: string } | null>(null);
  const [followCursor, setFollowCursor] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Deep-link initial state from URL (applied AFTER mount to avoid SSR hydration mismatch).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const runParam = q.get("run");
    if (runParam && epic.runs.some((r) => r.id === runParam)) setSelectedRunId(runParam);
    const cur = q.get("cursor");
    if (cur != null && !Number.isNaN(Number(cur))) setCursor(Number(cur));
    if (q.get("mode") === "LIVE_SIM") setMode("LIVE_SIM");
    const tab = q.get("tab");
    if (tab) setDetailTab(tab);
    const modalPath = q.get("modal");
    if (modalPath) {
      const r = runParam && epic.runs.some((x) => x.id === runParam) ? getRun(epic, runParam) : epic.runs[0];
      setModal({ title: modalPath, body: makeArtifactPreview({ run: r, path: modalPath, cursor: 0 }) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setPlaying(false);
  }, []);

  const tick = useCallback(() => {
    setCursor((c) => {
      const next = c + 1;
      if (next >= len) {
        stop();
        return len - 1;
      }
      return next;
    });
  }, [len, stop]);

  // LIVE SIM: auto-advance from first node.
  useEffect(() => {
    if (mode === "LIVE_SIM") {
      setPlaying(true);
      timer.current = setInterval(tick, speed);
      return () => {
        if (timer.current) clearInterval(timer.current);
      };
    }
    stop();
    return undefined;
  }, [mode, speed, tick, stop]);

  useEffect(() => () => stop(), [stop]);

  const selectRun = useCallback((runId: string) => {
    setSelectedRunId(runId);
    setCursor(0);
    setSelection({ kind: "run", id: runId });
  }, []);

  const onSelectNode = useCallback(
    (nodeId: string) => {
      // REPLAY click-to-rewind: clicking a node sets cursor to its route index.
      // LIVE_SIM click only inspects (no rewind) so the running stream continues.
      if (mode === "REPLAY") {
        const ix = getRouteIndex(run, nodeId);
        if (ix >= 0) setCursor(clampCursor(run, ix));
      }
      setSelection({ kind: "node", id: nodeId });
      setDetailTab("overview");
    },
    [mode, run],
  );

  const onOpenArtifact = useCallback(
    (path: string, kind: string) => {
      const r = getRun(epic, selectedRunId);
      const node =
        selection.kind === "node"
          ? r.gates.flatMap((g) => g.nodes).find((n) => n.id === selection.id)
          : undefined;
      const gate =
        selection.kind === "node"
          ? r.gates.find((g) => g.nodes.some((n) => n.id === selection.id))
          : undefined;
      void kind;
      setModal({
        title: path,
        body: makeArtifactPreview({ run: r, gate, node, path, cursor }),
      });
    },
    [epic, selectedRunId, selection, cursor],
  );

  const active = getActiveRoute(run, cursor);

  return (
    <div className="leg-root" data-testid="login-epic-run-graph-root">
      <header className="leg-header">
        <div>
          <h1>Login Epic — GWC Runtime Graph</h1>
          <p>Epic → 10 Runs → G0–G6 → Runtime Nodes. Each node owns fileReads / fileWrites / artifacts / runbook / TC &amp; Executor history / checkpoints.</p>
        </div>
        <div className="leg-chips">
          <span className="leg-chip">SIMULATED</span>
          <span className="leg-chip">{epic.epic_id}</span>
          <span className="leg-chip">{epic.run_count} RUNS</span>
          <span className="leg-chip">{epic.runtime_node_count} NODES</span>
          <span className="leg-chip">HISTORY OVERLAY VISUAL-ONLY</span>
        </div>
      </header>

      <EpicRunRail runs={epic.runs} selectedRunId={selectedRunId} onSelectRun={selectRun} />

      <section className="leg-main">
        <div className="leg-graph-col">
          <div className="leg-run-head">
            <h2>2 · Run-Level Graph — {run.id}</h2>
            <div className="leg-follow">
              <button
                data-testid="runtime-follow-cursor"
                data-follow={followCursor ? "on" : "off"}
                className={followCursor ? "on" : "off"}
                onClick={() => setFollowCursor((v) => !v)}
              >
                Follow: {followCursor ? "ON" : "OFF"}
              </button>
              <span className="leg-follow-note">manual pan disables Follow</span>
            </div>
          </div>
          <ReactFlowProvider>
            <RuntimeGraphCanvas
              run={run}
              cursor={cursor}
              selection={selection}
              followCursor={followCursor}
              onSelectNode={onSelectNode}
              onOpenArtifact={onOpenArtifact}
              onUserViewportInteract={() => setFollowCursor(false)}
            />
          </ReactFlowProvider>
        </div>

        <aside className="leg-side">
          <RuntimeDetailsPanel
            run={run}
            gate={
              selection.kind === "node"
                ? run.gates.find((g) => g.nodes.some((n) => n.id === selection.id))
                : undefined
            }
            node={
              selection.kind === "node"
                ? run.gates.flatMap((g) => g.nodes).find((n) => n.id === selection.id)
                : undefined
            }
            onOpen={onOpenArtifact}
          />
        </aside>
      </section>

      <RuntimePlayer
        cursor={cursor}
        len={len}
        mode={mode}
        speed={speed}
        playing={playing}
        label={`${active.gate_id} · ${active.node_id}`}
        onFirst={() => setCursor(0)}
        onPrev={() => setCursor((c) => clampCursor(run, c - 1))}
        onToggle={() => {
          if (playing) stop();
          else {
            setPlaying(true);
            timer.current = setInterval(tick, speed);
          }
        }}
        onNext={() => setCursor((c) => clampCursor(run, c + 1))}
        onLast={() => setCursor(len - 1)}
        onScrub={(c) => setCursor(clampCursor(run, c))}
        onMode={(m) => setMode(m)}
        onSpeed={(ms) => setSpeed(ms)}
      />

      {modal && <ArtifactModal path={modal.title} content={modal.body} onClose={() => setModal(null)} />}
    </div>
  );
}
