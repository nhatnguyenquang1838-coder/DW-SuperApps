/**
 * Fixture replay session — drives the deterministic replay reducer over the
 * materialized DWO-UR-30-V1 projection-events.jsonl.
 *
 * Wraps lib/runtime/replay.ts (ReplaySession) so the Fixture Lab can:
 *   - load the full event stream for a run
 *   - simulate progressive arrival (appendLive one event at a time)
 *   - reset to initial state
 *   - step forward / backward through durable positions
 *   - switch CURRENT <-> REPLAY
 *   - simulate reconnect + catch-up
 *
 * Never opens a LangGraph checkpointer. Never mutates projection_events.
 */

import { ReplaySession, type ReplayFrame, type SurfaceSnapshot } from '@/lib/replay';
import type { ProjectionEvent } from '@/lib/live';
import { DEV_RUN_020 } from '@/lib/dwo/fixtureSpec';

export const FIXTURE_EVENTS_PATH =
  'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl';

export interface FixtureReplaySession {
  readonly runId: string;
  readonly total: number;
  readonly mode: 'LIVE' | 'REPLAY';
  readonly cursor: number;
  readonly frame: ReplayFrame;
  readonly surfaces: SurfaceSnapshot;
  readonly synchronized: boolean;
  readonly events: readonly ProjectionEvent[];
  append(): FixtureReplaySession;
  reset(): FixtureReplaySession;
  stepBack(n?: number): FixtureReplaySession;
  stepForward(n?: number): FixtureReplaySession;
  rewindTo(cursor: number): FixtureReplaySession;
  enterReplay(cursor?: number): FixtureReplaySession;
  resumeLive(): FixtureReplaySession;
  simulateReconnect(catchUpToTip?: boolean): FixtureReplaySession;
  cursors(): readonly number[];
}

let _fs: typeof import('fs') | null = null;
let _path: typeof import('path') | null = null;

function ensureFs(): typeof import('fs') | null {
  if (_fs !== null) return _fs;
  try {
    _fs = require('fs');
    _path = require('path');
  } catch {
    // Client bundle cannot resolve fs — session is server-only.
  }
  return _fs;
}

function snapshotOf(
  runId: string,
  session: ReplaySession,
  api: {
    reset: () => FixtureReplaySession;
    stepBack: (n?: number) => FixtureReplaySession;
    stepForward: (n?: number) => FixtureReplaySession;
    rewindTo: (cursor: number) => FixtureReplaySession;
    enterReplay: (cursor?: number) => FixtureReplaySession;
    resumeLive: () => FixtureReplaySession;
    simulateReconnect: (catchUpToTip?: boolean) => FixtureReplaySession;
    cursors: () => readonly number[];
  },
): FixtureReplaySession {
  const frame = session.frame();
  const surfaces = session.surfaces();
  const stamps = [surfaces.rootCard, surfaces.dag, surfaces.timeline, surfaces.evidence, surfaces.inspector];
  const synchronized = stamps.every((s) => s.cursor === surfaces.cursor && s.stateDigest === surfaces.stateDigest);
  return {
    runId,
    total: session.total,
    mode: session.mode,
    cursor: session.cursor,
    frame,
    surfaces,
    synchronized,
    events: session.timeline().events,
    append: () => { session.appendLive(session.timeline().events[session.total] ?? undefined); return snapshotOf(runId, session, api); },
    reset: api.reset,
    stepBack: api.stepBack,
    stepForward: api.stepForward,
    rewindTo: api.rewindTo,
    enterReplay: api.enterReplay,
    resumeLive: api.resumeLive,
    simulateReconnect: api.simulateReconnect,
    cursors: api.cursors,
  };
}

function loadEventsForRun(
  runId: string,
  config: { path?: string; readText?: (path: string) => string } = {},
): ProjectionEvent[] {
  const fs = ensureFs();
  if (!fs) return [];
  const p = _path!;
  const filePath = config.path ?? p.join(process.cwd(), FIXTURE_EVENTS_PATH);
  let raw: string;
  try {
    raw = config.readText ? config.readText(filePath) : fs.readFileSync(filePath, 'utf-8');
  } catch {
    return [];
  }
  const events: ProjectionEvent[] = [];
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const obj = JSON.parse(trimmed) as Record<string, unknown>;
      if (obj.run_id === runId) {
        events.push(obj as ProjectionEvent);
      }
    } catch {
      continue;
    }
  }
  // Deterministic order by ordinal (same rule as globalDurableOrder for fixtures).
  events.sort((a, b) => {
    const ao = typeof a.ordinal === 'number' ? a.ordinal : 0;
    const bo = typeof b.ordinal === 'number' ? b.ordinal : 0;
    return ao - bo;
  });
  return events;
}

/**
 * Build a fixture replay session for a run.
 *
 * Starts in LIVE at the canonical tip (all events ingested).
 */
export function createFixtureReplaySession(
  runId: string,
  config: { path?: string; readText?: (path: string) => string } = {},
): FixtureReplaySession | null {
  // DEV-RUN-020 is an incompatible-source negative. Its pack row is evidence
  // for the negative case, not replayable canonical history. Do not manufacture
  // a session from that row; callers surface UNAVAILABLE/INCOMPATIBLE.
  if (runId === DEV_RUN_020) return null;
  const events = loadEventsForRun(runId, config);
  if (events.length === 0) return null;

  let session = new ReplaySession(events);

  const api = {
    reset: () => { session = new ReplaySession(events); return snapshotOf(runId, session, api); },
    stepBack: (n = 1) => { session = new ReplaySession(events); session.stepBack(n); return snapshotOf(runId, session, api); },
    stepForward: (n = 1) => { session = new ReplaySession(events); session.stepForward(n); return snapshotOf(runId, session, api); },
    rewindTo: (cursor: number) => { session = new ReplaySession(events); session.rewindTo(cursor); return snapshotOf(runId, session, api); },
    enterReplay: (cursor?: number) => { session = new ReplaySession(events); session.enterReplay(cursor); return snapshotOf(runId, session, api); },
    resumeLive: () => { session = new ReplaySession(events); session.resumeLive(); return snapshotOf(runId, session, api); },
    simulateReconnect: (catchUpToTip = true) => {
      session = new ReplaySession(events);
      if (catchUpToTip) session.resumeLive();
      return snapshotOf(runId, session, api);
    },
    cursors: () => new ReplaySession(events).timeline().cursors(),
  };

  return snapshotOf(runId, session, api);
}

/** Fixture replay grants no effect capability. */
export const FIXTURE_REPLAY_CAPABILITIES = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);