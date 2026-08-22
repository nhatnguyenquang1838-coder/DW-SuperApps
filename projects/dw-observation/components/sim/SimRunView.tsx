"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReplayMode, SimRun, TaskState } from "@/lib/simRun";
import {
  activeGateIdAt,
  buildTimeline,
  clampCursor,
  findTask,
  selectedTaskAt,
  taskStateAt,
} from "@/lib/simRun";
import GateContainer from "./GateContainer";
import Inspector from "./Inspector";
import ReplayControls from "./ReplayControls";

type Props = {
  run: SimRun;
};

/**
 * Controller for the G0-G6 simulated run view. Owns the only mutable UI state
 * (cursor, selected task, mode, speed, playing). All replay derivations are
 * delegated to the pure functions in lib/simRun.ts, so the component stays a
 * thin orchestrator over presentational children.
 */
export default function SimRunView({ run }: Props) {
  const timeline = useMemo(() => buildTimeline(run), [run]);
  const total = timeline.length;

  const [cursor, setCursor] = useState(0);
  const [requested, setRequested] = useState<string | undefined>(undefined);
  const [mode, setMode] = useState<ReplayMode>("REPLAY");
  const [speed, setSpeed] = useState(900);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
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
        if (c >= total - 1) {
          stop();
          return c;
        }
        const next = c + 1;
        setRequested(timeline[next].task_id);
        return next;
      });
    }, speed);
  }, [speed, stop, timeline, total]);

  useEffect(() => () => stop(), [stop]);

  const goTo = useCallback(
    (target: number) => {
      stop();
      const c = clampCursor(target, total);
      setCursor(c);
      setRequested(timeline[c].task_id);
    },
    [stop, timeline, total]
  );

  const onSelect = useCallback(
    (taskId: string) => {
      setRequested(taskId);
      if (mode === "REPLAY") {
        const i = timeline.findIndex((s) => s.task_id === taskId);
        if (i >= 0) goTo(i);
      }
    },
    [mode, timeline, goTo]
  );

  const onModeChange = useCallback(
    (m: ReplayMode) => {
      stop();
      setMode(m);
      if (m === "LIVE") {
        const last = total - 1;
        setCursor(last);
        setRequested(timeline[last].task_id);
      }
    },
    [stop, timeline, total]
  );

  const taskState = useCallback((taskId: string): TaskState => taskStateAt(run, taskId, cursor), [run, cursor]);

  const selectedId = selectedTaskAt(run, cursor, requested);
  const activeGateId = activeGateIdAt(run, cursor);
  const selected = findTask(run, selectedId);
  const playerLabel = selected ? `${selected.gate.label} · ${selected.task.task_title}` : "—";

  const expandAll = () => document.querySelectorAll(".sr-gate").forEach((g) => g.classList.remove("sr-gate-collapsed"));
  const collapseAll = () => document.querySelectorAll(".sr-gate").forEach((g) => g.classList.add("sr-gate-collapsed"));

  return (
    <div className="sr-app" data-testid="sr-app">
      <header className="sr-header">
        <div>
          <h1>DW Run Observatory — Simulated Full G0→G6 Run</h1>
          <div className="sr-sub">{run.title}</div>
        </div>
        <div className="sr-badges">
          <span className="sr-badge sr-good">SIMULATED RUN</span>
          <span className="sr-badge">{run.run_id}</span>
          <span className="sr-badge sr-violet">{total} TASK CARDS</span>
        </div>
      </header>

      <div className="sr-layout">
        <section className="sr-panel">
          <div className="sr-panel-head">
            <div>
              <h2>Gate Containers → Task Cards</h2>
              <div className="sr-sub">Card note nằm trong gate; connector animate theo replay cursor.</div>
            </div>
            <div className="sr-toolbar">
              <button className="sr-ctrl" data-testid="sr-expand-all" onClick={expandAll}>Expand all</button>
              <button className="sr-ctrl" data-testid="sr-collapse-all" onClick={collapseAll}>Collapse all</button>
            </div>
          </div>
          <div className="sr-graph">
            <div className="sr-summary" data-testid="sr-summary">
              {run.gates.map((g) => (
                <div className="sr-summary-card" key={g.id} data-testid="sr-summary-card">
                  <b>{g.tasks.length}</b>
                  <span>{g.label}</span>
                </div>
              ))}
            </div>
            <div data-testid="sr-gates">
              {run.gates.map((gate, i) => (
                <div key={gate.id}>
                  <GateContainer
                    gate={gate}
                    isActive={activeGateId === gate.id}
                    cursor={cursor}
                    selectedTaskId={selectedId}
                    taskState={taskState}
                    onSelect={onSelect}
                  />
                  {i < run.gates.length - 1 && <div className="sr-gate-link" aria-hidden="true" />}
                </div>
              ))}
            </div>
          </div>
          <ReplayControls
            cursor={cursor}
            timelineLength={total}
            mode={mode}
            speed={speed}
            playing={playing}
            onFirst={() => goTo(0)}
            onPrev={() => goTo(cursor - 1)}
            onPlayPause={play}
            onNext={() => goTo(cursor + 1)}
            onLast={() => goTo(total - 1)}
            onScrub={(v) => goTo(v)}
            onModeChange={onModeChange}
            onSpeedChange={setSpeed}
            playerLabel={playerLabel}
          />
        </section>

        <aside className="sr-panel sr-inspector-panel">
          <div className="sr-panel-head">
            <div>
              <h2>Task / Artifact Details</h2>
              <div className="sr-sub">Click card để xem chi tiết. REPLAY click sẽ rewind.</div>
            </div>
            <span className="sr-badge sr-good" data-testid="sr-mode-badge">{mode}</span>
          </div>
          {selected && (
            <Inspector
              task={selected.task}
              gate={selected.gate}
              mode={mode}
              timelineLength={total}
              cursor={cursor}
            />
          )}
          <div className="sr-note">{run.source_note}</div>
        </aside>
      </div>
    </div>
  );
}
