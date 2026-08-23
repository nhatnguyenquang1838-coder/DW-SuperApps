"use client";

// M3 — replay controls + synchronized whole-screen rewind surface.
//
// One `ReplaySession` drives EVERY pane. The five surfaces (RootCard, DAG,
// timeline, CI/evidence, inspector) are rendered from a single `SurfaceSnapshot`,
// so a rewind moves the entire screen to the same point in history — panes
// cannot drift apart because they are not computed independently.
//
// Read-only: no mutation, no publish, no credential. Replay is a pure cursor
// over events the live client already loaded. Entering replay never drops live
// frames — they append to the canonical tip and appear on resume.

import { useCallback, useMemo, useState } from "react";
import type { ProjectionEvent } from "@/lib/live";
import {
  ReplaySession,
  UNKNOWN,
  isSynchronized,
  type ReplayMode,
  type SurfaceSnapshot,
} from "@/lib/replay";

export interface ReplayPaneProps {
  runId: string;
  events: ProjectionEvent[];
  /** True when the durable read was denied/unconfigured (never a fake LIVE). */
  storeDegraded?: boolean;
}

export default function ReplayPane({ runId, events, storeDegraded = false }: ReplayPaneProps) {
  const session = useMemo(() => new ReplaySession(events), [events]);
  const [snapshot, setSnapshot] = useState<SurfaceSnapshot>(() => session.surfaces());

  const sync = useCallback(() => setSnapshot(session.surfaces()), [session]);

  const rewindTo = useCallback(
    (cursor: number) => {
      session.rewindTo(cursor);
      sync();
    },
    [session, sync]
  );

  const resumeLive = useCallback(() => {
    session.resumeLive();
    sync();
  }, [session, sync]);

  const mode: ReplayMode = snapshot.mode;
  const synchronized = isSynchronized(snapshot);

  if (session.total === 0) {
    return (
      <section aria-label="Replay" data-testid="replay-pane">
        <h2>Replay</h2>
        <p data-testid="replay-empty">
          {storeDegraded
            ? "PROJECTION_UNAVAILABLE — durable history unreadable; nothing to replay."
            : "No projection events to replay."}
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Replay" data-testid="replay-pane">
      <header>
        <h2>Replay</h2>
        <span data-testid="replay-mode">{mode}</span>
        <span data-testid="replay-cursor">
          {snapshot.cursor}/{snapshot.total}
        </span>
        <span data-testid="replay-digest">{snapshot.stateDigest}</span>
        <span data-testid="replay-sync">
          {synchronized ? "SYNCHRONIZED" : "DESYNC"}
        </span>
      </header>

      <div role="group" aria-label="Replay controls">
        <button
          type="button"
          data-testid="replay-start"
          onClick={() => rewindTo(0)}
          disabled={snapshot.cursor === 0}
        >
          Start
        </button>
        <button
          type="button"
          data-testid="replay-back"
          onClick={() => rewindTo(snapshot.cursor - 1)}
          disabled={snapshot.cursor === 0}
        >
          Step back
        </button>
        <button
          type="button"
          data-testid="replay-forward"
          onClick={() => rewindTo(snapshot.cursor + 1)}
          disabled={snapshot.cursor === snapshot.total}
        >
          Step forward
        </button>
        <button
          type="button"
          data-testid="replay-tip"
          onClick={() => rewindTo(snapshot.total)}
          disabled={snapshot.cursor === snapshot.total}
        >
          Tip
        </button>
        <button type="button" data-testid="replay-resume" onClick={resumeLive}>
          Resume LIVE
        </button>
        <input
          type="range"
          aria-label="Replay position"
          data-testid="replay-scrub"
          min={0}
          max={snapshot.total}
          value={snapshot.cursor}
          onChange={(e) => rewindTo(Number(e.target.value))}
        />
      </div>

      {/* Every pane below is stamped with the SAME cursor + digest. */}
      <div data-testid="surface-root-card" data-cursor={snapshot.rootCard.cursor}>
        <h3>RootCard</h3>
        <dl>
          <dt>Run</dt>
          <dd data-testid="root-run-id">{String(snapshot.rootCard.runId ?? UNKNOWN)}</dd>
          <dt>Started</dt>
          <dd>{String(snapshot.rootCard.startedAt ?? UNKNOWN)}</dd>
          <dt>Applied</dt>
          <dd data-testid="root-applied">
            {String(snapshot.rootCard.eventsApplied)} of {String(snapshot.rootCard.totalEvents)}
          </dd>
          <dt>Anomalies</dt>
          <dd data-testid="root-anomaly-count">{String(snapshot.rootCard.anomalyCount)}</dd>
        </dl>
      </div>

      <div data-testid="surface-dag" data-cursor={snapshot.dag.cursor}>
        <h3>DAG</h3>
        <ul>
          {Object.entries(
            snapshot.dag.nodes as Record<string, { node: string; status: string }>
          ).map(([key, n]) => (
            <li key={key} data-testid={`dag-node-${key}`}>
              {n.node}: {n.status}
            </li>
          ))}
        </ul>
        <ul>
          {Object.entries(
            snapshot.dag.gates as Record<string, { gate: string; status: string }>
          ).map(([key, g]) => (
            <li key={key} data-testid={`dag-gate-${key}`}>
              {g.gate}: {g.status}
            </li>
          ))}
        </ul>
      </div>

      <div data-testid="surface-timeline" data-cursor={snapshot.timeline.cursor}>
        <h3>Timeline</h3>
        <p data-testid="timeline-pending">{String(snapshot.timeline.pendingCount)} pending</p>
        <ol>
          {(
            snapshot.timeline.applied as Array<{
              sourceEventId: string;
              eventType: string;
              sequence: number | null;
            }>
          ).map((e, i) => (
            <li key={`${e.sourceEventId}-${i}`} data-testid={`timeline-event-${e.sourceEventId}`}>
              {e.sequence === null ? UNKNOWN : e.sequence} · {e.eventType}
            </li>
          ))}
        </ol>
      </div>

      <div data-testid="surface-evidence" data-cursor={snapshot.evidence.cursor}>
        <h3>CI / Evidence</h3>
        <ul>
          {(snapshot.evidence.refs as Array<{ sourceEventId: string; ref: string }>).map(
            (r, i) => (
              <li key={`${r.sourceEventId}-${i}`} data-testid="evidence-ref">
                {r.ref}
              </li>
            )
          )}
        </ul>
        <p data-testid="evidence-authority">
          {(snapshot.evidence.authorityRefs as string[]).join(", ") || UNKNOWN}
        </p>
      </div>

      <div data-testid="surface-inspector" data-cursor={snapshot.inspector.cursor}>
        <h3>Inspector</h3>
        <ul>
          {(
            snapshot.inspector.anomalies as Array<{ kind: string; message: string }>
          ).map((a, i) => (
            <li key={i} data-testid={`inspector-anomaly-${a.kind}`}>
              {a.kind}: {a.message}
            </li>
          ))}
        </ul>
        <p data-testid="inspector-selected">
          {snapshot.inspector.selected
            ? String(
                (snapshot.inspector.selected as { sourceEventId: string }).sourceEventId
              )
            : UNKNOWN}
        </p>
      </div>

      <p data-testid="replay-note">
        Replay is a read-only projection of immutable history for run {runId}. It
        creates no authority and mutates nothing; LIVE resumes at the canonical
        tip with sequence state intact.
      </p>
    </section>
  );
}
