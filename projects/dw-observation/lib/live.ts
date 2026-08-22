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
  // Source ledger sequence. PRESERVED as UNKNOWN when absent — we never
  // fabricate a sequence (e.g. `seq ?? 0`). Events without a valid numeric
  // sequence are excluded from live sequencing (gap/stale logic) but are still
  // retained as observation records.
  sequence?: number;
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
    // UNKNOWN (missing) sequence is excluded from high-water math: treat it as
    // the low sentinel so it never fabricates ordering.
    const seq = typeof e.sequence === "number" ? e.sequence : -1;
    hw[e.source_system] = Math.max(hw[e.source_system] ?? -1, seq);
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
  // Optional change listener: invoked after every state mutation (bootstrap,
  // replay, live frame, resync, transport-down) so a UI binding (e.g. the
  // React hook) can re-render. Keeps the client framework-agnostic.
  onChange?: () => void;
  // Frames received before historical bootstrap completes are buffered (not
  // dropped) and replayed once the snapshot is ready. This closes the
  // bootstrap/subscription/reconnect frame-loss window (G3 rework item 4):
  // subscribing before bootstrap() means a frame can arrive while projection
  // is still null, and we must not silently reject it.
  private bootstrapped = false;
  private preBootstrapBuffer: unknown[] = [];

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
    // Mark ready, then replay any frames buffered during the bootstrap gap so
    // none are silently dropped (frame-loss window closure).
    this.bootstrapped = true;
    const buffered = this.preBootstrapBuffer;
    this.preBootstrapBuffer = [];
    for (const frame of buffered) {
      this.receiveLive(frame);
    }
    this.emitChange();
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
    // Before the historical snapshot is ready, buffer frames instead of
    // rejecting them — they are replayed once bootstrap() completes.
    if (!this.bootstrapped) {
      this.preBootstrapBuffer.push(message);
      return { kind: "APPENDED", appended: false };
    }
    const envelope = (message as { event?: unknown })?.event;
    if (!envelope || typeof envelope !== "object") {
      this.lastError = "live frame missing 'event' envelope";
      this.emitChange();
      return { kind: "REJECTED" };
    }
    const evt = envelope as ProjectionEvent;
    if (!evt.source_system || !evt.source_event_id) {
      this.lastError = "invalid live envelope (missing source identity)";
      this.emitChange();
      return { kind: "REJECTED" };
    }
    if (evt.run_id !== this.runId) {
      return { kind: "REJECTED" };
    }

    // Preserve UNKNOWN: never fabricate a sequence. An event without a valid
    // numeric sequence is retained as an observation record but EXCLUDED from
    // live sequencing (no gap/stale math on a missing sequence).
    const seq = typeof evt.sequence === "number" ? evt.sequence : null;

    const src = evt.source_system;
    const hw = this.highWater[src] ?? -1;

    const dup = this.events.some(
      (e) => e.source_system === src && e.source_event_id === evt.source_event_id
    );
    if (dup) {
      this.emitChange();
      return { kind: "DUPLICATE" };
    }

    if (seq === null) {
      // No source sequence: keep as observation-only, do not mutate sequence
      // high-water or state. Record nothing anomalous (it is a valid record).
      this.events.push(evt);
      this.state = "LIVE";
      this.lastError = undefined;
      this.emitChange();
      return { kind: "APPENDED", appended: true };
    }

    const expected = hw + 1;
    if (seq > expected) {
      const anomaly: LiveAnomaly = {
        kind: "GAP",
        at_index: this.events.length,
        source_system: src,
        source_event_id: evt.source_event_id,
        message: `live sequence gap at (${src}): seq=${seq} expected next ${expected}; awaiting historical catch-up`,
      };
      this.anomalies.push(anomaly);
      this.state = "CATCHING_UP";
      this.emitChange();
      return { kind: "GAP", anomaly };
    }

    const prev = this.events.length;
    this.events.push(evt);
    this.highWater[src] = Math.max(hw, seq);
    this.state = "LIVE";
    this.lastError = undefined;

    // Stale: non-duplicate behind the high-water mark for this source.
    if (seq < hw && hw >= 0) {
      const anomaly: LiveAnomaly = {
        kind: "STALE",
        at_index: prev,
        source_system: src,
        source_event_id: evt.source_event_id,
        message: `stale live event at (${src}): seq=${seq} behind high-water ${hw}`,
      };
      this.anomalies.push(anomaly);
      this.emitChange();
      return { kind: "STALE", anomaly };
    }
    this.emitChange();
    return { kind: "APPENDED", appended: true };
  }

  private emitChange(): void {
    if (typeof this.onChange === "function") {
      this.onChange();
    }
  }

  markTransportDown(): void {
    this.state = this.events.length > 0 ? "PROJECTION_UNAVAILABLE" : "UNAVAILABLE";
    this.lastError = "realtime transport unavailable";
    this.emitChange();
  }

  close(): void {
    this.transport.close();
  }
}
