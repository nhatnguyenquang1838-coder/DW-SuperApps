"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReplayMode, SimRun, Selection, NodeState } from "@/lib/simRun";
import {
  activeGateIdAt,
  buildTimeline,
  clampCursor,
  getGate,
  getNode,
  isGateActiveAt,
  nodeStateAt,
  selectedNodeAt,
  timelineLength,
} from "@/lib/simRun";
import GateContainer from "./GateContainer";
import Inspector from "./Inspector";
import ReplayControls from "./ReplayControls";

type Props = { run: SimRun };

/** Deterministic synthetic artifact body (no real secrets/config). */
function artifactContent(
  run: SimRun,
  path: string,
  kind: string,
  gate: SimGateLike,
  node: SimNodeLike | undefined,
): string {
  const base = {
    run_id: run.run_id,
    task_id: run.task_id,
    repository: run.repository,
    base_sha: run.base_sha,
    gate: gate?.id,
    artifact_path: path,
    kind,
  };
  if (path.endsWith(".yaml") || path.endsWith(".yml")) {
    return [
      `run_id: ${base.run_id}`,
      `task_id: ${base.task_id}`,
      `repository: ${base.repository}`,
      `gate: ${base.gate}`,
      `node_id: ${node?.node_id ?? "gate-summary"}`,
      `node_family: ${node?.family ?? "gate"}`,
      `artifact_path: ${path}`,
      `status: ${node ? nodeStateAt(run, gate.id, node.node_id, 0) : "gate"}`,
      `source_basis:`,
      `  - core/GATE_LIFECYCLE_CONTRACT_v1.0.md`,
      `  - schemas/node-architect/runtime-node.schema.json`,
      `evidence:`,
      ...(node?.reads ?? gate?.gate_artifacts ?? []).map((x) => `  - ${x}`),
    ].join("\n");
  }
  if (path.endsWith(".json")) {
    return JSON.stringify(
      {
        ...base,
        node: node
          ? {
              node_id: node.node_id,
              family: node.family,
              node_type: node.node_type,
              authority_boundary: node.authority_boundary,
              source_status: node.source_status,
              maturity: node.maturity,
              declared_gates: node.declared_gates,
              implementation_refs: node.implementation_refs,
            }
          : null,
        gate_history: gate
          ? {
              taskcontroller: gate.taskcontroller_history,
              executor: gate.executor_history,
            }
          : null,
      },
      null,
      2,
    );
  }
  return `${path}\n\nReferenced by ${node?.node_id ?? gate?.id}.`;
}

type SimGateLike = SimRun["gates"][number];
type SimNodeLike = SimGateLike["nodes"][number];

export default function SimRunView({ run }: Props) {
  const timeline = useMemo(() => buildTimeline(run), [run]);
  const len = timeline.length;

  const [cursor, setCursor] = useState(0);
  const [mode, setMode] = useState<ReplayMode>("REPLAY");
  const [speed, setSpeed] = useState(750);
  const [playing, setPlaying] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [selection, setSelection] = useState<Selection>(() =>
    selectedNodeAt(run, 0),
  );
  const [modal, setModal] = useState<{ title: string; body: string } | null>(
    null,
  );
  const [activeTab, setActiveTab] = useState("overview");

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const worldRef = useRef<HTMLDivElement | null>(null);
  const inspectorRef = useRef<HTMLDivElement | null>(null);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setPlaying(false);
  }, []);

  const play = useCallback(() => {
    if (timer.current) {
      stop();
      return;
    }
    setPlaying(true);
    timer.current = setInterval(() => {
      setCursor((c) => {
        if (c >= len - 1) {
          stop();
          return c;
        }
        const next = c + 1;
        const step = timeline[next];
        setSelection({ kind: "node", gateId: step.gate_id, nodeId: step.node_id });
        return next;
      });
    }, speed);
  }, [len, speed, stop, timeline]);

  // Cleanup on unmount.
  useEffect(() => () => stop(), [stop]);

  // When mode flips to LIVE, restart from 0 and play.
  useEffect(() => {
    if (mode === "LIVE") {
      stop();
      setCursor(0);
      const step = timeline[0];
      setSelection({ kind: "node", gateId: step.gate_id, nodeId: step.node_id });
      play();
    } else {
      stop();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const goTo = useCallback(
    (c: number) => {
      stop();
      const clamped = clampCursor(run, c);
      setCursor(clamped);
      setSelection(selectedNodeAt(run, clamped));
    },
    [run, stop],
  );

  const zoomTo = (z: number) => {
    const next = Math.max(0.55, Math.min(1.8, z));
    setZoom(next);
    if (worldRef.current)
      worldRef.current.style.transform = `scale(${next})`;
  };

  const openArtifact = (path: string, kind: string) => {
    const gate =
      selection.kind === "node"
        ? getGate(run, selection.gateId)
        : getGate(run, selection.gateId);
    const node =
      selection.kind === "node"
        ? getNode(run, selection.gateId, selection.nodeId)
        : undefined;
    setModal({
      title: path,
      body: artifactContent(run, path, kind, gate ?? run.gates[0], node),
    });
  };

  // Tab switching (delegated DOM since panes are static markup).
  const selectTab = (tab: string) => {
    setActiveTab(tab);
    if (inspectorRef.current) {
      inspectorRef.current
        .querySelectorAll<HTMLElement>(".sr-tab")
        .forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
      inspectorRef.current
        .querySelectorAll<HTMLElement>(".sr-tab-pane")
        .forEach((p) => {
          p.hidden = p.dataset.pane !== tab;
          p.classList.toggle("active", p.dataset.pane === tab);
        });
    }
  };

  // Wire tab clicks once.
  useEffect(() => {
    if (!inspectorRef.current) return;
    const tabs = inspectorRef.current.querySelectorAll<HTMLElement>(".sr-tab");
    tabs.forEach((t) =>
      t.addEventListener("click", () => selectTab(t.dataset.tab ?? "overview")),
    );
    return () => {
      tabs.forEach((t) =>
        t.removeEventListener("click", () => selectTab(t.dataset.tab ?? "overview")),
      );
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection]);

  const selectedGate = getGate(run, selection.kind === "node" ? selection.gateId : selection.gateId);
  const selectedNode =
    selection.kind === "node"
      ? getNode(run, selection.gateId, selection.nodeId)
      : undefined;

  return (
    <div className="sr-app">
      <header className="sr-header">
        <div>
          <h1>DW Run Observatory — Corrected Node Architect View</h1>
          <div className="sr-sub">
            Gate → Runtime Nodes. Mỗi node chứa artifacts, runbook, TaskController
            history, Executor history, checkpoint.
          </div>
        </div>
        <div className="sr-badges">
          <span className="sr-badge sr-good">SIMULATED RUN</span>
          <span className="sr-badge">{run.run_id}</span>
          <span className="sr-badge sr-violet">{len} NODE CARDS</span>
          <span className="sr-badge sr-warn">HISTORY OVERLAY VISUAL-ONLY</span>
        </div>
      </header>

      <div className="sr-layout">
        <section className="sr-panel">
          <div className="sr-panel-head">
            <div>
              <h2>Gate Containers → Runtime Node Cards</h2>
              <div className="sr-sub">
                Source-aligned: node registry + runtime graph + durable
                run-history overlay semantics.
              </div>
            </div>
            <div className="sr-toolbar">
              <button className="sr-ctrl" onClick={() => zoomTo(zoom - 0.1)}>
                −
              </button>
              <span className="sr-zoom-pill">{Math.round(zoom * 100)}%</span>
              <button className="sr-ctrl" onClick={() => zoomTo(zoom + 0.1)}>
                +
              </button>
              <button className="sr-ctrl" onClick={() => zoomTo(1)}>
                Reset
              </button>
              <button
                className="sr-ctrl"
                onClick={() =>
                  document
                    .querySelectorAll(".sr-gate")
                    .forEach((g) => g.classList.remove("collapsed"))
                }
              >
                Expand
              </button>
              <button
                className="sr-ctrl"
                onClick={() =>
                  document
                    .querySelectorAll(".sr-gate")
                    .forEach((g) => g.classList.add("collapsed"))
                }
              >
                Collapse
              </button>
            </div>
          </div>

          <div className="sr-graph-shell">
            <div className="sr-world" ref={worldRef}>
              <div className="sr-summary">
                {run.gates.map((g) => (
                  <div className="sr-summary-card" key={g.id}>
                    <b>{g.nodes.length}</b>
                    <span>{g.label}</span>
                    <span>
                      {g.gate_artifacts.length} gate artifacts ·{" "}
                      {g.taskcontroller_history.length} TC events ·{" "}
                      {g.executor_history.length} exec events
                    </span>
                  </div>
                ))}
              </div>

              {run.gates.map((g, gi) => (
                <div key={g.id}>
                  <GateContainer
                    gate={g}
                    run={run}
                    cursor={cursor}
                    active={isGateActiveAt(run, g.id, cursor)}
                    selection={selection}
                    onSelectNode={(gateId, nodeId) => {
                      stop();
                      setSelection({ kind: "node", gateId, nodeId });
                      setCursor(clampCursor(run, timeline.findIndex(
                        (s) => s.gate_id === gateId && s.node_id === nodeId,
                      )));
                    }}
                    onSelectGate={(gateId) => {
                      stop();
                      setSelection({ kind: "gate", gateId });
                    }}
                  />
                  {gi < run.gates.length - 1 && <div className="sr-gate-link" />}
                </div>
              ))}
            </div>
          </div>

          <ReplayControls
            cursor={cursor}
            timelineLength={len}
            mode={mode}
            speed={speed}
            playing={playing}
            label={
              selectedNode
                ? `${selectedGate?.label} · ${selectedNode.title}`
                : (selectedGate?.label ?? "")
            }
            onFirst={() => goTo(0)}
            onPrev={() => goTo(cursor - 1)}
            onPlayToggle={play}
            onNext={() => goTo(cursor + 1)}
            onLast={() => goTo(len - 1)}
            onScrub={goTo}
            onMode={(m) => setMode(m)}
            onSpeed={(ms) => setSpeed(ms)}
          />
        </section>

        <aside className="sr-panel sr-inspector">
          <div className="sr-panel-head">
            <div>
              <h2>Node / Gate Inspector</h2>
              <div className="sr-sub">
                Artifacts, runbook, controller/executor history.
              </div>
            </div>
            <span className="sr-badge sr-good">{mode}</span>
          </div>
          <div className="sr-body" ref={inspectorRef}>
            <Inspector
              selection={selection}
              gate={selectedGate ?? run.gates[0]}
              node={selectedNode}
              onOpenArtifact={openArtifact}
            />
          </div>
          <div className="sr-note">
            Theo source: registry adapter giữ canonical runtime nodes; run-history
            adapter overlay run/event/checkpoint history và đánh dấu history edges
            là visual-only. UI này mô phỏng đúng nguyên tắc đó.
          </div>
        </aside>
      </div>

      {modal && (
        <div className="sr-modal-backdrop" onClick={() => setModal(null)}>
          <div className="sr-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sr-modal-head">
              <div className="sr-modal-title">{modal.title}</div>
              <button className="sr-close" onClick={() => setModal(null)}>
                Close
              </button>
            </div>
            <pre className="sr-modal-body">{modal.body}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
