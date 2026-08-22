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
  // Durable global cross-source order, assigned by Postgres (projection_ordinal
  // BIGINT GENERATED ALWAYS AS IDENTITY). Used for historical ORDER BY only.
  projection_ordinal?: number;
  // Provenance timestamp (data only; NOT used for ordering).
  occurred_at?: string;
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
// The transport reports connection STATUS to the client via onStatus so the
// client can gate LIVE on its durable-history readiness latch.
export interface RealtimeTransport {
  subscribe(topic: string, onMessage: (payload: unknown) => void): void;
  close(): void;
  // Connection-status callback. The transport attaches its listeners BEFORE
  // calling subscribe() and reports SUBSCRIBED/CHANNEL_ERROR/etc. The client
  // decides whether SUBSCRIBED implies LIVE (it does NOT — durable latch rules).
  onStatus?: (status: string, suggestedState: LiveState) => void;
}

export type ReceiveKind =
  | "APPENDED"
  | "DUPLICATE"
  | "GAP"
  | "STALE"
  | "REJECTED"
  | "BUFFERED";

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

// Global durable ordering (seq=16 + R4_B6 correction): ordered ONLY by the
// durable global projection_ordinal (assigned by Postgres at insert), so mixed
// TC/GWC interleaving is preserved exactly as recorded. Events WITHOUT a
// projection_ordinal keep their RELATIVE INPUT ORDER — they are NEVER reordered
// or source-grouped. occurred_at is NOT used for ordering. The durable DB
// history (which always carries projection_ordinal) therefore never falls back
// to per-source grouping.
export function globalDurableOrder(events: ProjectionEvent[]): ProjectionEvent[] {
  const indexed = events.map((e, i) => ({ e, i }));
  indexed.sort((A, B) => {
    const oa = A.e.projection_ordinal;
    const ob = B.e.projection_ordinal;
    const ha = typeof oa === "number";
    const hb = typeof ob === "number";
    if (ha && hb) return oa - ob; // both durable -> order by ordinal
    if (ha !== hb) return ha ? -1 : 1; // ordinal events precede no-ordinal
    // Neither has an ordinal: keep INPUT order (stable) — no source grouping.
    return A.i - B.i;
  });
  return indexed.map((x) => x.e);
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

  // F1: explicit transport status listener (registered via setStatusListener
  // BEFORE bindTransport). SUBSCRIBED does NOT force canonical LIVE.
  private statusListener?: (status: string, suggestedState: LiveState) => void;

  // --- Readiness latch (F2): LIVE requires BOTH durable history ready AND the
  // transport connected. Neither alone forces LIVE. ---
  private durableReady = false; // bootstrap()/resync() completed with data-or-allowed-empty
  private transportReady = false; // transport reported SUBSCRIBED
  // Distinguishes the INITIAL subscribe from a RECONNECT (after a prior
  // disconnect/error). A reconnect must durable-resync before LIVE (R4_B2).
  private hasConnected = false;

  // Frames received before historical bootstrap completes are buffered (not
  // dropped) and replayed once the snapshot is ready. This closes the
  // bootstrap/subscription/reconnect frame-loss window.
  private bootstrapped = false;
  private preBootstrapBuffer: unknown[] = [];

  constructor(store: EventStore, transport: RealtimeTransport, runId: string) {
    this.store = store;
    this.transport = transport;
    this.runId = runId;
    // Wire the status listener immediately (F1): a SUBSCRIBED/CHANNEL_ERROR
    // transition can arrive before or without an explicit bindTransport(), so
    // it must never be missed. handleStatus owns the transportReady latch; the
    // external statusListener (registered via setStatusListener) is forwarded.
    this.transport.onStatus = (status, suggested) => {
      this.handleStatus(status);
      this.statusListener?.(status, suggested);
    };
  }

  // Recompute the effective state from the readiness latch. LIVE only when both
  // durable history and the transport are ready AND we have at least one event.
  private recomputeState(): void {
    if (this.events.length === 0) {
      // No data: never present LIVE. Degrade honestly.
      this.state = this.durableReady
        ? "PROJECTION_UNAVAILABLE"
        : "UNAVAILABLE";
      return;
    }
    if (this.durableReady && this.transportReady) {
      this.state = "LIVE";
    } else if (this.durableReady && !this.transportReady) {
      // Durable history present but transport not yet connected: we still show
      // the snapshot; the projection is available but not live-streaming.
      this.state = "PROJECTION_UNAVAILABLE";
    } else {
      this.state = "CATCHING_UP";
    }
  }

  // Historical catch-up (bootstrap + reconnect). Source of truth.
  async bootstrap(): Promise<void> {
    const loaded = await this.store.loadAll(this.runId);
    this.events = globalDurableOrder(loaded.slice());
    this.highWater = highWaterOf(this.events);
    this.durableReady = true;
    this.bootstrapped = true;

    const buffered = this.preBootstrapBuffer;
    this.preBootstrapBuffer = [];
    this.recomputeState();
    this.lastError =
      this.events.length > 0 ? undefined : "historical store empty or read denied";

    for (const frame of buffered) {
      this.receiveLive(frame);
    }
    this.emitChange();
  }

  // Reconnect flow (F3): real durable resync -> reconcile -> resume LIVE.
  // Triggered on GAP or transport reconnect. Returns true on success.
  async resync(): Promise<boolean> {
    try {
      const fresh = await this.store.loadAll(this.runId);
      // Reconcile: durable source of truth replaces the in-memory list; any
      // buffered live frames that arrived during the gap are re-applied after.
      const buffered = this.preBootstrapBuffer;
      this.preBootstrapBuffer = [];
      this.events = globalDurableOrder(fresh.slice());
      this.highWater = highWaterOf(this.events);
      this.durableReady = true;
      // F4: an empty resync must NOT present LIVE.
      this.recomputeState();
      this.lastError =
        this.events.length > 0 ? undefined : "historical store empty or read denied";
      for (const frame of buffered) {
        this.receiveLive(frame);
      }
      this.emitChange();
      return true;
    } catch (err) {
      this.state = this.events.length > 0 ? "PROJECTION_UNAVAILABLE" : "UNAVAILABLE";
      this.lastError = `durable store unreachable during resync: ${String(err)}`;
      this.emitChange();
      return false;
    }
  }

  // F1: explicit status-listener registration. The host/hook MUST call this
  // BEFORE bindTransport()/subscribe so the initial SUBSCRIBED/CHANNEL_ERROR
  // transition is never missed. SUBSCRIBED alone does NOT force canonical LIVE
  // — the client gates LIVE on its durable-history readiness latch.
  setStatusListener(cb: (status: string, suggestedState: LiveState) => void): void {
    this.statusListener = cb;
  }

  bindTransport(): void {
    // Attach the status listener BEFORE subscribe (F1) so we never miss the
    // initial SUBSCRIBED/CHANNEL_ERROR transition. The client owns the internal
    // transportReady latch (handleStatus); it ALSO forwards to the external
    // statusListener if one was registered.
    this.transport.onStatus = (status, suggested) => {
      this.handleStatus(status);
      this.statusListener?.(status, suggested);
    };
    this.transport.subscribe(this.runId, (payload) => this.receiveLive(payload));
  }

  // Internal: update the readiness latch from transport status. SUBSCRIBED sets
  // transportReady; channel errors clear it. SUBSCRIBED alone does NOT force
  // LIVE — recomputeState() gates LIVE on BOTH durableReady AND transportReady.
  // A SUBSCRIBED arrival AFTER a prior disconnect/error is a RECONNECT and must
  // perform a durable resync (store.loadAll) before LIVE (R4_B2). Status casing
  // is normalized defensively (R4_B3) so a lowercase "closed" still clears the
  // latch even if a transport forgets to normalize at its boundary.
  private handleStatus(rawStatus: string): void {
    const status = String(rawStatus).toUpperCase();
    if (status === "SUBSCRIBED") {
      if (!this.hasConnected) {
        // Initial subscribe: transport is up; LIVE still gated on durable latch.
        this.hasConnected = true;
        this.transportReady = true;
      } else {
        // Reconnect after a prior disconnect/error: MUST durable-resync before
        // promoting to LIVE. Enter CATCHING_UP and defer LIVE until the resync
        // succeeds — single loadAll, NO busy-loop.
        this.state = "CATCHING_UP";
        this.transportReady = false;
        this.durableReady = false; // require fresh durable confirmation
        this.emitChange();
        void this.reconnectResync();
        return;
      }
    } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
      this.transportReady = false;
    }
    this.recomputeState();
    this.emitChange();
  }

  // Reconnect reconcile: real durable resync, then promote to LIVE ONLY after
  // the durable store is successfully re-read. If the store is unreachable the
  // observer stays degraded and never falsely presents LIVE (R4_B2/B3).
  private async reconnectResync(): Promise<void> {
    const ok = await this.resync();
    if (ok) {
      this.transportReady = true;
      this.recomputeState();
    } else {
      this.transportReady = false;
    }
    this.emitChange();
  }

  // Normalize a real Supabase Broadcast envelope (F9, protocol per seq=16):
  //   { type: "broadcast", event: "projection_event", payload: <ProjectionEvent> }
  // topic (the channel) is "observatory:<run_id>" — distinct from the event
  // name. We extract payload as the canonical ProjectionEvent. Two legacy/
  // inline shapes are also accepted for test ergonomics:
  //   { event: <ProjectionEvent> }            (event field IS the event object)
  //   <ProjectionEvent>                        (message itself is the event)
  private normalizeEnvelope(message: unknown): ProjectionEvent | null {
    if (!message || typeof message !== "object") return null;
    const m = message as { type?: unknown; event?: unknown; payload?: unknown };
    // Real Broadcast envelope: event === "projection_event", payload is the event.
    if (
      (m.type === "broadcast" || m.type === undefined) &&
      m.event === "projection_event" &&
      m.payload &&
      typeof m.payload === "object"
    ) {
      return m.payload as ProjectionEvent;
    }
    // Legacy inline shape: { event: <ProjectionEvent> } — the event field holds
    // the ProjectionEvent object directly.
    if (m.event && typeof m.event === "object" && (m.event as ProjectionEvent).source_system) {
      return m.event as ProjectionEvent;
    }
    // Bare ProjectionEvent: the message itself is the event.
    if ((message as ProjectionEvent).source_system) {
      return message as ProjectionEvent;
    }
    return null;
  }

  receiveLive(message: unknown): ReceiveResult {
    // Before the historical snapshot is ready, buffer frames instead of
    // rejecting them — they are replayed once bootstrap() completes.
    if (!this.bootstrapped) {
      this.preBootstrapBuffer.push(message);
      return { kind: "BUFFERED", appended: false };
    }
    const evt = this.normalizeEnvelope(message);
    if (!evt) {
      this.lastError = "live frame missing valid envelope";
      this.emitChange();
      return { kind: "REJECTED" };
    }
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
      // No source sequence: keep as observation-only, appended to the end (not
      // sorted into the durable ordinal stream). Preserves the record without
      // mutating high-water or reordering sequenced events.
      this.events.push(evt);
      this.recomputeState();
      this.lastError = undefined;
      this.emitChange();
      return { kind: "APPENDED", appended: true };
    }

    const expected = hw + 1;
    // Only treat as a GAP when we actually have a known baseline for this
    // source (hw >= 0). A first-seen source with no durable history has no
    // intermediate events to detect a gap against, so the frame appends.
    if (hw >= 0 && seq > expected) {
      const anomaly: LiveAnomaly = {
        kind: "GAP",
        at_index: this.events.length,
        source_system: src,
        source_event_id: evt.source_event_id,
        message: `live sequence gap at (${src}): seq=${seq} expected next ${expected}; awaiting historical catch-up`,
      };
      this.anomalies.push(anomaly);
      // F3: a GAP means we are missing intermediate durable history — go to
      // CATCHING_UP and trigger a REAL durable resync to reconcile.
      this.state = "CATCHING_UP";
      this.emitChange();
      void this.resync();
      return { kind: "GAP", anomaly };
    }

    const prev = this.events.length;
    this.events = globalDurableOrder([...this.events, evt]);
    this.highWater[src] = Math.max(hw, seq);
    this.recomputeState();
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
    this.transportReady = false;
    this.recomputeState();
    this.lastError = "realtime transport unavailable";
    this.emitChange();
  }

  close(): void {
    this.transport.close();
  }
}
