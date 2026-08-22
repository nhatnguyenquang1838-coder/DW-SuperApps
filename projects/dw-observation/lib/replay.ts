// M3 — deterministic replay + synchronized whole-screen rewind (browser side).
//
// This is the TypeScript peer of `dw_observation/replay.py` and follows the SAME
// contract, so a replay computed in the UI can never disagree with the Python
// projection:
//
//   * `RunState(N) = reduce(events[0..N])` — a frame is a fold of a PREFIX.
//   * Supplied order IS replay order. Nothing is re-sorted by occurred_at.
//   * DUPLICATE / OUT_OF_ORDER / STALE / GAP are surfaced explicitly, never
//     hidden, using the same vocabulary as `lib/live.ts` and the M0 reducer.
//   * Rewinding is a pure cursor move over an APPEND-ONLY stream: it never
//     truncates, reorders, or drops events, so LIVE can resume with identical
//     sequence/high-water state.
//   * Unknown source values stay explicitly UNKNOWN — replay never invents a
//     value (no `seq ?? 0`).
//
// This module performs NO remote mutation and holds no credential: it is a pure
// read-only projection over events the live client already fetched.

import type { LiveAnomaly, ProjectionEvent } from "@/lib/live";
import { globalDurableOrder } from "@/lib/live";

export const UNKNOWN = "—";

export type ReplayMode = "LIVE" | "REPLAY";

export const ANOMALY_KINDS = ["DUPLICATE", "OUT_OF_ORDER", "STALE", "GAP"] as const;
export type AnomalyKind = (typeof ANOMALY_KINDS)[number];

export interface ReplayNodeState {
  node: string;
  status: string;
  lastEventSeq: number;
}

export interface ReplayGateState {
  gate: string;
  status: string;
  approvedBy: string;
  releasedBy: string;
  failedBy: string;
  authorityRef: string;
  lastEventSeq: number;
}

export interface ReplayProjection {
  runId: string | null;
  startedAt: string | null;
  lastEventAt: string | null;
  events: ProjectionEvent[];
  nodes: Record<string, ReplayNodeState>;
  gates: Record<string, ReplayGateState>;
  anomalies: LiveAnomaly[];
}

export interface ReplayFrame {
  cursor: number;
  total: number;
  atStart: boolean;
  atTip: boolean;
  projection: ReplayProjection;
  anomalies: LiveAnomaly[];
  stateDigest: string;
}

// ---------------------------------------------------------------------------
// Deterministic digest (stable stringify + FNV-1a 64-bit, hex)
// ---------------------------------------------------------------------------

// Sorted-key stringify so a digest depends on VALUES, never on key insertion
// order. Mirrors Python's json.dumps(sort_keys=True, separators=(",",":")).
export function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return `{${keys
      .map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`)
      .join(",")}}`;
  }
  return "null";
}

// FNV-1a 64-bit over the canonical string. Deterministic, dependency-free, and
// sufficient for state-equality comparison in the UI (it is NOT a security or
// governance digest and is never used as authority evidence).
export function digestOf(value: unknown): string {
  const s = stableStringify(value);
  let hi = 0xcbf29ce4 >>> 0;
  let lo = 0x84222325 >>> 0;
  for (let i = 0; i < s.length; i++) {
    lo ^= s.charCodeAt(i) & 0xff;
    // multiply by the FNV prime 0x100000001b3 using 32-bit halves
    const loMul = lo * 0x1b3 + hi * 0x00000100;
    const hiMul = hi * 0x1b3 + Math.floor((lo * 0x1b3) / 0x100000000) + lo * 0x00000001;
    lo = loMul >>> 0;
    hi = hiMul >>> 0;
  }
  const hex = (n: number) => n.toString(16).padStart(8, "0");
  return `${hex(hi)}${hex(lo)}`;
}

// ---------------------------------------------------------------------------
// Reducer (prefix fold) — parity with dw_observation/reducer.py
// ---------------------------------------------------------------------------

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" && v.length > 0 ? v : fallback;
}

function actorLabel(v: unknown): string {
  if (typeof v === "string" && v.length > 0) return v;
  if (v && typeof v === "object") {
    const a = v as Record<string, unknown>;
    const parts = [str(a.kind), str(a.id)].filter((x) => x.length > 0);
    if (parts.length > 0) return parts.join(":");
  }
  return UNKNOWN;
}

function emptyProjection(): ReplayProjection {
  return {
    runId: null,
    startedAt: null,
    lastEventAt: null,
    events: [],
    nodes: {},
    gates: {},
    anomalies: [],
  };
}

function gateOf(proj: ReplayProjection, gate: string): ReplayGateState {
  if (!proj.gates[gate]) {
    proj.gates[gate] = {
      gate,
      status: "none",
      approvedBy: UNKNOWN,
      releasedBy: UNKNOWN,
      failedBy: UNKNOWN,
      authorityRef: UNKNOWN,
      lastEventSeq: -1,
    };
  }
  return proj.gates[gate];
}

// Gate semantics preserved verbatim from the source (parity with M0):
// passed -> "passed", failed -> "failed" (NOT released), approved -> "approved",
// released -> "released".
const GATE_TRANSITIONS: Record<string, { status: string; actorField: keyof ReplayGateState }> = {
  gate_passed: { status: "passed", actorField: "approvedBy" },
  gate_approved: { status: "approved", actorField: "approvedBy" },
  gate_released: { status: "released", actorField: "releasedBy" },
  gate_failed: { status: "failed", actorField: "failedBy" },
};

const NODE_EVENTS = new Set(["node_progress", "node_started", "node_completed"]);

/**
 * Fold an ordered event prefix into a projection.
 *
 * Anomaly detection is per SOURCE SYSTEM (TC and GWC are independent ledgers),
 * exactly as the Python reducer does, so interleaving two sources never raises a
 * false GAP/OUT_OF_ORDER/STALE.
 */
export function reduceEvents(events: ProjectionEvent[]): ReplayProjection {
  const proj = emptyProjection();
  const seen = new Set<string>();
  const hwSeq: Record<string, number> = {};
  const hwTime: Record<string, string | null> = {};

  events.forEach((e, idx) => {
    const src = str(e.source_system, UNKNOWN);
    const eid = str(e.source_event_id, UNKNOWN);
    const identity = `${src}\u0000${eid}`;
    // Preserve UNKNOWN: never fabricate a sequence.
    const seq = typeof e.sequence === "number" ? e.sequence : null;
    const occurredAt = typeof e.occurred_at === "string" ? e.occurred_at : null;
    const curSeq = hwSeq[src] ?? -1;
    const curTime = hwTime[src] ?? null;

    if (seen.has(identity)) {
      proj.anomalies.push({
        kind: "DUPLICATE",
        at_index: idx,
        source_system: src,
        source_event_id: eid,
        message: `duplicate source identity (${src}, ${eid}) at index ${idx}`,
      });
    } else {
      seen.add(identity);
    }

    if (seq !== null) {
      if (idx > 0 && curSeq >= 0 && seq < curSeq) {
        proj.anomalies.push({
          kind: "OUT_OF_ORDER",
          at_index: idx,
          source_system: src,
          source_event_id: eid,
          message: `source sequence regressed at index ${idx} (${src}): seq=${seq} < high-water seq=${curSeq}`,
        });
      }
      if (
        curTime !== null &&
        occurredAt !== null &&
        (occurredAt < curTime || (occurredAt === curTime && seq < curSeq))
      ) {
        proj.anomalies.push({
          kind: "STALE",
          at_index: idx,
          source_system: src,
          source_event_id: eid,
          message: `stale event at index ${idx} (${src}): (occurred_at=${occurredAt}, seq=${seq}) behind high-water (occurred_at=${curTime}, seq=${curSeq})`,
        });
      }
      if (idx > 0 && curSeq >= 0 && seq > curSeq && seq !== curSeq + 1) {
        proj.anomalies.push({
          kind: "GAP",
          at_index: idx,
          source_system: src,
          source_event_id: eid,
          message: `sequence gap at index ${idx} (${src}): seq=${seq}, prior max=${curSeq}`,
        });
      }
      // Monotone high-water advance on (occurred_at, sequence).
      if (
        curTime === null ||
        (occurredAt !== null &&
          (occurredAt > curTime || (occurredAt === curTime && seq > curSeq)))
      ) {
        hwTime[src] = occurredAt;
        hwSeq[src] = seq;
      }
    }

    proj.events.push(e);
    if (proj.runId === null && typeof e.run_id === "string" && e.run_id.length > 0) {
      proj.runId = e.run_id;
    }
    if (occurredAt !== null) proj.lastEventAt = occurredAt;

    applyEvent(proj, e, seq ?? -1);
  });

  return proj;
}

function applyEvent(proj: ReplayProjection, e: ProjectionEvent, seq: number): void {
  const eventType = str((e as Record<string, unknown>).event_type);
  const authorityRef = str((e as Record<string, unknown>).authority_ref, UNKNOWN);
  const actor = actorLabel((e as Record<string, unknown>).actor);

  if (eventType === "run_started") {
    const occurredAt = typeof e.occurred_at === "string" ? e.occurred_at : null;
    proj.startedAt = occurredAt;
    if (typeof e.run_id === "string" && e.run_id.length > 0) proj.runId = e.run_id;
    return;
  }

  const gateTransition = GATE_TRANSITIONS[eventType];
  if (gateTransition) {
    const gateName = str((e as Record<string, unknown>).gate);
    if (gateName.length === 0) return;
    const g = gateOf(proj, gateName);
    if (g.lastEventSeq <= seq || g.status === "none") {
      g.status = gateTransition.status;
      (g[gateTransition.actorField] as string) = actor;
      g.authorityRef = authorityRef;
      g.lastEventSeq = seq;
    }
    return;
  }

  if (NODE_EVENTS.has(eventType)) {
    const nodeId = str((e as Record<string, unknown>).node_id);
    if (nodeId.length === 0) return;
    if (!proj.nodes[nodeId]) {
      proj.nodes[nodeId] = { node: nodeId, status: "pending", lastEventSeq: -1 };
    }
    const n = proj.nodes[nodeId];
    if (n.lastEventSeq <= seq || n.status === "pending") {
      const outcome = str((e as Record<string, unknown>).outcome);
      const after = (e as Record<string, unknown>).after as Record<string, unknown> | undefined;
      const afterStatus = after ? str(after.status) : "";
      n.status = outcome || afterStatus || n.status;
      n.lastEventSeq = seq;
    }
  }
  // Any other event_type is observation-only (parity with the Python reducer).
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

function projectionShape(proj: ReplayProjection) {
  // Digest input: state only (no incidental object identity), sorted for stability.
  return {
    run_id: proj.runId,
    started_at: proj.startedAt,
    last_event_at: proj.lastEventAt,
    nodes: proj.nodes,
    gates: proj.gates,
    anomalies: proj.anomalies.map((a) => ({
      kind: a.kind,
      at_index: a.at_index,
      source_system: a.source_system ?? null,
      source_event_id: a.source_event_id ?? null,
    })),
    applied: proj.events.map((e) => ({
      source_system: e.source_system,
      source_event_id: e.source_event_id,
      sequence: typeof e.sequence === "number" ? e.sequence : null,
    })),
  };
}

export class ReplayTimeline {
  private readonly items: ProjectionEvent[];

  constructor(events: ProjectionEvent[]) {
    // Hold our own copy: the timeline never mutates the caller's array.
    this.items = events.slice();
  }

  get events(): ProjectionEvent[] {
    return this.items.slice();
  }

  get total(): number {
    return this.items.length;
  }

  get runId(): string | null {
    for (const e of this.items) {
      if (typeof e.run_id === "string" && e.run_id.length > 0) return e.run_id;
    }
    return null;
  }

  clamp(cursor: number): number {
    if (!Number.isFinite(cursor)) return 0;
    const c = Math.trunc(cursor);
    if (c < 0) return 0;
    if (c > this.total) return this.total;
    return c;
  }

  cursors(): number[] {
    return Array.from({ length: this.total + 1 }, (_, i) => i);
  }

  frameAt(cursor: number): ReplayFrame {
    const c = this.clamp(cursor);
    const proj = reduceEvents(this.items.slice(0, c));
    return {
      cursor: c,
      total: this.total,
      atStart: c === 0,
      atTip: c === this.total,
      projection: proj,
      anomalies: proj.anomalies,
      stateDigest: digestOf(projectionShape(proj)),
    };
  }

  tip(): ReplayFrame {
    return this.frameAt(this.total);
  }

  start(): ReplayFrame {
    return this.frameAt(0);
  }

  frames(): ReplayFrame[] {
    return this.cursors().map((c) => this.frameAt(c));
  }

  /** Digest over EVERY intermediate frame, not just the tip. */
  replayDigest(): string {
    return digestOf({
      run_id: this.runId,
      total: this.total,
      frames: this.frames().map((f) => ({ cursor: f.cursor, digest: f.stateDigest })),
    });
  }

  verifyDeterminism(repeats = 3): boolean {
    const passes = Math.max(2, repeats);
    const first = this.frames().map((f) => f.stateDigest).join("|");
    for (let i = 1; i < passes; i++) {
      if (this.frames().map((f) => f.stateDigest).join("|") !== first) return false;
    }
    return true;
  }

  rewindSequence(cursors: number[]): ReplayFrame[] {
    return cursors.map((c) => this.frameAt(c));
  }

  isPathConsistent(cursors: number[]): boolean {
    const seen = new Map<number, string>();
    for (const c of cursors) {
      const f = this.frameAt(c);
      const prev = seen.get(f.cursor);
      if (prev !== undefined && prev !== f.stateDigest) return false;
      seen.set(f.cursor, f.stateDigest);
    }
    return true;
  }
}

// ---------------------------------------------------------------------------
// Whole-screen surface projection
// ---------------------------------------------------------------------------

export interface SurfaceStamp {
  cursor: number;
  stateDigest: string;
}

export interface SurfaceSnapshot {
  cursor: number;
  total: number;
  mode: ReplayMode;
  stateDigest: string;
  rootCard: SurfaceStamp & Record<string, unknown>;
  dag: SurfaceStamp & Record<string, unknown>;
  timeline: SurfaceStamp & Record<string, unknown>;
  evidence: SurfaceStamp & Record<string, unknown>;
  inspector: SurfaceStamp & Record<string, unknown>;
}

export function surfacesOf(snapshot: SurfaceSnapshot): Record<string, SurfaceStamp> {
  return {
    rootCard: snapshot.rootCard,
    dag: snapshot.dag,
    timeline: snapshot.timeline,
    evidence: snapshot.evidence,
    inspector: snapshot.inspector,
  };
}

/** Every surface must agree on cursor AND state digest. */
export function isSynchronized(snapshot: SurfaceSnapshot): boolean {
  return Object.values(surfacesOf(snapshot)).every(
    (s) => s.cursor === snapshot.cursor && s.stateDigest === snapshot.stateDigest
  );
}

export function anomalyKindCounts(anomalies: LiveAnomaly[]): Record<AnomalyKind, number> {
  const counts = { DUPLICATE: 0, OUT_OF_ORDER: 0, STALE: 0, GAP: 0 };
  for (const a of anomalies) {
    if (a.kind in counts) counts[a.kind as AnomalyKind] += 1;
  }
  return counts;
}

/** Fan ONE frame out to every visible surface, so panes cannot disagree. */
export function projectSurfaces(frame: ReplayFrame, mode: ReplayMode = "REPLAY"): SurfaceSnapshot {
  const stamp: SurfaceStamp = { cursor: frame.cursor, stateDigest: frame.stateDigest };
  const proj = frame.projection;
  const head = frame.cursor > 0 ? proj.events[proj.events.length - 1] : null;

  const rootCard = {
    ...stamp,
    runId: proj.runId ?? UNKNOWN,
    startedAt: proj.startedAt ?? UNKNOWN,
    lastEventAt: proj.lastEventAt ?? UNKNOWN,
    eventsApplied: frame.cursor,
    totalEvents: frame.total,
    atTip: frame.atTip,
    mode,
    anomalyCount: frame.anomalies.length,
  };

  const dag = { ...stamp, nodes: proj.nodes, gates: proj.gates };

  const timeline = {
    ...stamp,
    applied: proj.events.map((e) => ({
      sequence: typeof e.sequence === "number" ? e.sequence : null,
      sourceSystem: str(e.source_system, UNKNOWN),
      sourceEventId: str(e.source_event_id, UNKNOWN),
      eventType: str((e as Record<string, unknown>).event_type, UNKNOWN),
      occurredAt: typeof e.occurred_at === "string" ? e.occurred_at : UNKNOWN,
    })),
    pendingCount: frame.total - frame.cursor,
    head: head
      ? {
          sourceEventId: str(head.source_event_id, UNKNOWN),
          eventType: str((head as Record<string, unknown>).event_type, UNKNOWN),
        }
      : null,
  };

  const refs: Array<{ sourceEventId: string; ref: string }> = [];
  const authorityRefs = new Set<string>();
  for (const e of proj.events) {
    const raw = (e as Record<string, unknown>).evidence_refs;
    if (Array.isArray(raw)) {
      for (const r of raw) {
        refs.push({
          sourceEventId: str(e.source_event_id, UNKNOWN),
          ref: typeof r === "string" ? r : stableStringify(r),
        });
      }
    }
    const auth = str((e as Record<string, unknown>).authority_ref);
    if (auth.length > 0) authorityRefs.add(auth);
  }
  const evidence = {
    ...stamp,
    refs,
    authorityRefs: Array.from(authorityRefs).sort(),
  };

  const inspector = {
    ...stamp,
    anomalies: frame.anomalies.map((a) => ({ kind: a.kind, message: a.message, atIndex: a.at_index })),
    anomalyKinds: anomalyKindCounts(frame.anomalies),
    selected: head
      ? {
          sourceEventId: str(head.source_event_id, UNKNOWN),
          before: (head as Record<string, unknown>).before ?? {},
          after: (head as Record<string, unknown>).after ?? {},
          actor: actorLabel((head as Record<string, unknown>).actor),
        }
      : null,
  };

  return {
    cursor: frame.cursor,
    total: frame.total,
    mode,
    stateDigest: frame.stateDigest,
    rootCard,
    dag,
    timeline,
    evidence,
    inspector,
  };
}

// ---------------------------------------------------------------------------
// Session: LIVE <-> REPLAY with uncorrupted resume
// ---------------------------------------------------------------------------

export class ReplaySession {
  private items: ProjectionEvent[];
  private modeValue: ReplayMode = "LIVE";
  private cursorValue: number;

  constructor(events: ProjectionEvent[] = []) {
    // Durable global order is applied ONCE at ingest (same rule as live.ts);
    // replay itself never re-sorts.
    this.items = globalDurableOrder(events.slice());
    this.cursorValue = this.items.length;
  }

  get mode(): ReplayMode {
    return this.modeValue;
  }

  get cursor(): number {
    return this.cursorValue;
  }

  get total(): number {
    return this.items.length;
  }

  get isReplaying(): boolean {
    return this.modeValue === "REPLAY";
  }

  timeline(): ReplayTimeline {
    return new ReplayTimeline(this.items);
  }

  /** Append a live event to the canonical tip; allowed in BOTH modes. */
  appendLive(event: ProjectionEvent): number {
    this.items = globalDurableOrder([...this.items, event]);
    if (this.modeValue === "LIVE") this.cursorValue = this.items.length;
    return this.items.length;
  }

  extendLive(events: ProjectionEvent[]): number {
    for (const e of events) this.appendLive(e);
    return this.items.length;
  }

  enterReplay(cursor?: number): ReplayFrame {
    this.modeValue = "REPLAY";
    this.cursorValue = this.timeline().clamp(cursor === undefined ? this.total : cursor);
    return this.frame();
  }

  rewindTo(cursor: number): ReplayFrame {
    this.modeValue = "REPLAY";
    this.cursorValue = this.timeline().clamp(cursor);
    return this.frame();
  }

  stepBack(n = 1): ReplayFrame {
    return this.rewindTo(this.cursorValue - Math.max(0, n));
  }

  stepForward(n = 1): ReplayFrame {
    return this.rewindTo(this.cursorValue + Math.max(0, n));
  }

  /** Return to LIVE at the canonical tip — identical to never having replayed. */
  resumeLive(): ReplayFrame {
    this.modeValue = "LIVE";
    this.cursorValue = this.items.length;
    return this.frame();
  }

  frame(): ReplayFrame {
    return this.timeline().frameAt(this.cursorValue);
  }

  surfaces(): SurfaceSnapshot {
    return projectSurfaces(this.frame(), this.modeValue);
  }

  rewindPath(cursors: number[]): SurfaceSnapshot[] {
    return cursors.map((c) => {
      this.rewindTo(c);
      return this.surfaces();
    });
  }
}
