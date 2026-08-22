// M2 — read-only live projection client (DW Run Observatory).
//
// Source of truth = the durable projection event store (Postgres in prod).
// Supabase Realtime Broadcast is TRANSPORT ONLY and is never canonical history.
// On reconnect: historical catch-up -> sequence reconcile -> resume LIVE.
// Gaps / duplicates / stale sequences are detected explicitly and surfaced.
// A temporary Realtime failure degrades to PROJECTION_UNAVAILABLE while the
// last known historical snapshot is retained -- it never fails the canonical
// runtime. This module performs NO remote mutation (no DB write, no broadcast
// publish); it is a read-only consumer.

export type LiveState =
  | "UNAVAILABLE"
  | "LIVE"
  | "CATCHING_UP"
  | "DEGRADED"
  | "PROJECTION_UNAVAILABLE";

export interface ProjectionEvent {
  run_id: string;
  source_system: string;
  source_event_id: string;
  sequence: number;
  [key: string]: unknown;
}

export interface LiveAnomaly {
  kind: "DUPLICATE" | "OUT_OF_ORDER" | "STALE" | "GAP";
  at_index: number;
  source_system?: string;
  source_event_id?: string;
  message: string;
}

// Read-only durable store. The host supplies a Postgres-backed implementation;
// the in-memory version in tests/local dev never performs remote mutation.
export interface EventStore {
  loadAll(runId: string): ProjectionEvent[] | Promise<ProjectionEvent[]>;
}

// Supabase Realtime Broadcast transport (subscribe only). Never publishes.
export interface RealtimeTransport {
  subscribe(topic: string, onMessage: (payload: unknown) => void): void;
  close(): void;
}

export type ReceiveKind =
  | "APPENDED"
  | "DUPLICATE"
  | "GAP"
  | "STALE"
  | "REJECTED";

export interface ReceiveResult {
  kind: ReceiveKind;
  anomaly?: LiveAnomaly;
  appended?: boolean;
}

function highWaterOf(events: ProjectionEvent[]): Record<string, number> {
  const hw: Record<string, number> = {};
  for (const e of events) {
    hw[e.source_system] = Math.max(hw[e.source_system] ?? -1, e.sequence);
  }
  return hw;
}

export class LiveProjectionClient {
  readonly runId: string;
  private store: EventStore;
  private transport: RealtimeTransport;
  state: LiveState = "UNAVAILABLE";
  events: ProjectionEvent[] = [];
  highWater: Record<string, number> = {};
  anomalies: LiveAnomaly[] = [];
  lastError?: string;

  constructor(store: EventStore, transport: RealtimeTransport, runId: string) {
    this.store = store;
    this.transport = transport;
    this.runId = runId;
  }

  // Historical catch-up (bootstrap + reconnect). Source of truth.
  async bootstrap(): Promise<void> {
    const loaded = await this.store.loadAll(this.runId);
    this.events = loaded.slice();
    this.highWater = highWaterOf(this.events);
    this.state = "LIVE";
    this.lastError = undefined;
  }

  // Reconnect flow: historical catch-up -> sequence reconcile -> resume LIVE.
  async resync(): Promise<boolean> {
    try {
      const fresh = await this.store.loadAll(this.runId);
      this.events = fresh.slice();
      this.highWater = highWaterOf(this.events);
      this.state = "LIVE";
      this.lastError = undefined;
      return true;
    } catch (err) {
      this.state = this.events.length > 0 ? "PROJECTION_UNAVAILABLE" : "UNAVAILABLE";
      this.lastError = `durable store unreachable during resync: ${String(err)}`;
      return false;
    }
  }

  bindTransport(): void {
    this.transport.subscribe(this.runId, (payload) => this.receiveLive(payload));
  }

  receiveLive(message: unknown): ReceiveResult {
    if (this.state === "UNAVAILABLE" || this.events.length === 0) {
      this.state = "UNAVAILABLE";
      return { kind: "REJECTED" };
    }
    const envelope = (message as { event?: unknown })?.event;
    if (!envelope || typeof envelope !== "object") {
      this.lastError = "live frame missing 'event' envelope";
      return { kind: "REJECTED" };
    }
    const evt = envelope as ProjectionEvent;
    if (!evt.source_system || !evt.source_event_id || typeof evt.sequence !== "number") {
      this.lastError = "invalid live envelope";
      return { kind: "REJECTED" };
    }
    if (evt.run_id !== this.runId) {
      return { kind: "REJECTED" };
    }

    const src = evt.source_system;
    const hw = this.highWater[src] ?? -1;

    const dup = this.events.some(
      (e) => e.source_system === src && e.source_event_id === evt.source_event_id
    );
    if (dup) {
      return { kind: "DUPLICATE" };
    }

    const expected = hw + 1;
    if (evt.sequence > expected) {
      const anomaly: LiveAnomaly = {
        kind: "GAP",
        at_index: this.events.length,
        source_system: src,
        source_event_id: evt.source_event_id,
        message: `live sequence gap at (${src}): seq=${evt.sequence} expected next ${expected}; awaiting historical catch-up`,
      };
      this.anomalies.push(anomaly);
      this.state = "CATCHING_UP";
      return { kind: "GAP", anomaly };
    }

    const prev = this.events.length;
    this.events.push(evt);
    this.highWater[src] = Math.max(hw, evt.sequence);
    this.state = "LIVE";
    this.lastError = undefined;

    // Stale: non-duplicate behind the high-water mark for this source.
    if ((evt.sequence) < hw && hw >= 0) {
      const anomaly: LiveAnomaly = {
        kind: "STALE",
        at_index: prev,
        source_system: src,
        source_event_id: evt.source_event_id,
        message: `stale live event at (${src}): seq=${evt.sequence} behind high-water ${hw}`,
      };
      this.anomalies.push(anomaly);
      return { kind: "STALE", anomaly };
    }
    return { kind: "APPENDED", appended: true };
  }

  markTransportDown(): void {
    this.state = this.events.length > 0 ? "PROJECTION_UNAVAILABLE" : "UNAVAILABLE";
    this.lastError = "realtime transport unavailable";
  }

  close(): void {
    this.transport.close();
  }
}
