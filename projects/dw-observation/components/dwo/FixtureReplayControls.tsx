"use client";

/**
 * Deterministic, read-only replay controls for the DWO-UR-30-V1 Fixture Lab.
 *
 * Uses the SAME ReplaySession reducer as the live/replay workspace. Fixture
 * events are immutable props; the controls only simulate their arrival. Reset
 * discards the client session, catch-up appends the remaining event stream, and
 * CURRENT/REPLAY only move the local cursor/mode. There is no write capability.
 */
import { useRef, useState } from "react";
import { ReplaySession, isSynchronized } from "@/lib/replay";
import type { ProjectionEvent } from "@/lib/live";

export default function FixtureReplayControls({
  runId,
  events,
}: {
  runId: string;
  events: readonly ProjectionEvent[];
}) {
  const sessionRef = useRef(new ReplaySession([]));
  const arrivedRef = useRef(0);
  const [, setRevision] = useState(0);
  const refresh = () => setRevision((n) => n + 1);

  if (events.length === 0) {
    return (
      <section className="dwo-fixture-replay" data-testid="fixture-replay-unavailable">
        <h2>Fixture replay</h2>
        <p>No fixture events for {runId} — replay unavailable (fail-closed).</p>
      </section>
    );
  }

  const session = sessionRef.current;
  const frame = session.frame();
  const applied = session.timeline().events.slice(0, frame.cursor);
  const mode = session.mode === "LIVE" ? "CURRENT" : "REPLAY";
  const synchronized = isSynchronized(session.surfaces());
  const canArrive = arrivedRef.current < events.length;

  const arriveNext = () => {
    if (!canArrive) return;
    session.appendLive(events[arrivedRef.current]);
    arrivedRef.current += 1;
    refresh();
  };

  const reset = () => {
    sessionRef.current = new ReplaySession([]);
    arrivedRef.current = 0;
    refresh();
  };

  const catchUp = () => {
    const remaining = events.slice(arrivedRef.current);
    session.extendLive([...remaining]);
    arrivedRef.current = events.length;
    session.resumeLive();
    refresh();
  };

  const enterReplay = () => {
    session.enterReplay();
    refresh();
  };

  const returnCurrent = () => {
    session.resumeLive();
    refresh();
  };

  return (
    <section
      className="dwo-fixture-replay"
      data-testid="fixture-replay-controls"
      data-run-id={runId}
    >
      <header className="dwo-fixture-replay-header">
        <div>
          <h2>Fixture replay</h2>
          <p>Read-only event arrival simulation · DWO-UR-30-V1</p>
        </div>
        <div className="dwo-fixture-replay-status" aria-live="polite">
          <span data-testid="fixture-replay-mode">{mode}</span>
          <span data-testid="fixture-replay-cursor">{frame.cursor}/{frame.total}</span>
          <span data-testid="fixture-replay-sync">
            {synchronized ? "SYNCHRONIZED" : "DESYNC"}
          </span>
        </div>
      </header>

      <div className="dwo-fixture-replay-actions" role="group" aria-label="Fixture replay controls">
        <button type="button" data-testid="fixture-event-arrive" onClick={arriveNext} disabled={!canArrive}>
          Arrive next event
        </button>
        <button type="button" data-testid="fixture-catch-up" onClick={catchUp}>
          Reconnect + catch up
        </button>
        <button type="button" data-testid="fixture-replay-reset" onClick={reset}>
          Reset
        </button>
        <button type="button" data-testid="fixture-mode-current" onClick={returnCurrent}>
          CURRENT
        </button>
        <button type="button" data-testid="fixture-mode-replay" onClick={enterReplay}>
          REPLAY
        </button>
        <button
          type="button"
          data-testid="fixture-replay-start"
          onClick={() => { session.rewindTo(0); refresh(); }}
          disabled={frame.cursor === 0}
        >
          Start
        </button>
        <button
          type="button"
          data-testid="fixture-replay-back"
          onClick={() => { session.stepBack(); refresh(); }}
          disabled={frame.cursor === 0}
        >
          Step back
        </button>
        <button
          type="button"
          data-testid="fixture-replay-forward"
          onClick={() => { session.stepForward(); refresh(); }}
          disabled={frame.cursor === frame.total}
        >
          Step forward
        </button>
      </div>

      <div className="dwo-fixture-replay-digest">
        State digest <code data-testid="fixture-replay-digest">{frame.stateDigest}</code>
      </div>
      <ol className="dwo-fixture-replay-events" data-testid="fixture-replay-events">
        {applied.map((event, index) => (
          <li key={`${event.source_system ?? "fixture"}:${event.source_event_id ?? event.event_id ?? index}:${index}`}>
            <span>{typeof event.sequence === "number" ? event.sequence : "UNKNOWN"}</span>
            <code>{String(event.source_event_id ?? event.event_id ?? "UNKNOWN")}</code>
            <span>{String(event.event_type ?? "fixture_projection_snapshot")}</span>
            {typeof event.gate_state === "string" && <span>{String(event.gate ?? "UNKNOWN")} {event.gate_state}</span>}
            {typeof event.run_state === "string" && <span>run {event.run_state}</span>}
          </li>
        ))}
      </ol>

      <style>{`
        .dwo-fixture-replay { margin-top: 24px; padding: 16px; border: 1px solid var(--dwo-color-border-default); border-radius: 8px; background: var(--dwo-color-bg-surface); color: var(--dwo-color-text-primary); }
        .dwo-fixture-replay-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 12px; }
        .dwo-fixture-replay-header h2 { margin: 0; font-size: 15px; font-weight: 700; }
        .dwo-fixture-replay-header p { margin: 4px 0 0; font-size: 11px; color: var(--dwo-color-text-muted); }
        .dwo-fixture-replay-status, .dwo-fixture-replay-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
        .dwo-fixture-replay-status span { padding: 3px 7px; border: 1px solid var(--dwo-color-border-default); border-radius: 4px; font: 10px ui-monospace, monospace; }
        .dwo-fixture-replay-actions button { padding: 5px 8px; border: 1px solid var(--dwo-color-border-default); border-radius: 5px; background: var(--dwo-color-bg-subtle); color: var(--dwo-color-text-primary); font-size: 11px; cursor: pointer; }
        .dwo-fixture-replay-actions button:hover:not(:disabled) { border-color: var(--dwo-color-accent-blue); }
        .dwo-fixture-replay-actions button:focus-visible { outline: 2px solid var(--dwo-color-accent-blue); outline-offset: 2px; }
        .dwo-fixture-replay-actions button:disabled { opacity: .45; cursor: not-allowed; }
        .dwo-fixture-replay-digest { margin-top: 12px; color: var(--dwo-color-text-muted); font-size: 10px; }
        .dwo-fixture-replay-digest code { margin-left: 6px; color: var(--dwo-color-text-faint); }
        .dwo-fixture-replay-events { margin: 10px 0 0; padding-left: 20px; color: var(--dwo-color-text-muted); font: 10px ui-monospace, monospace; }
        .dwo-fixture-replay-events li { display: flex; flex-wrap: wrap; gap: 8px; padding: 3px 0; }
        @media (max-width: 640px) { .dwo-fixture-replay-header { display: block; } .dwo-fixture-replay-status { margin-top: 8px; } }
      `}</style>
    </section>
  );
}
