"use client";

// React binding for the read-only live projection client (M2).
//
// Mounts the observer against an injected store + transport. The store/transport
// are supplied by the host app (Postgres + Supabase in prod) so this hook stays
// a read-only consumer with no remote mutation.
//
// Frame-loss window (G3 rework item 4): the observer subscribes to the transport
// BEFORE bootstrapping from the durable store. A frame that arrives after
// subscribe() but before the first historical snapshot would otherwise be
// applied against an empty high-water mark. We close that window by:
//   1. binding transport first (so the handler is live before any snapshot);
//   2. routing every frame through the SAME sync() that re-reads full client
//      state, so a late frame advances the view exactly once;
//   3. taking a post-bootstrap snapshot (sync) so any frame that landed during
//      bootstrap is already reflected when the view first renders.

import { useEffect, useRef, useState } from "react";
import {
  EventStore,
  LiveProjectionClient,
  LiveState,
  RealtimeTransport,
} from "@/lib/live";

export interface LiveProjectionView {
  state: LiveState;
  anomalies: { kind: string; message: string }[];
  eventCount: number;
  lastError?: string;
}

export function useLiveProjection(
  runId: string,
  store: EventStore,
  transport: RealtimeTransport
): LiveProjectionView {
  const clientRef = useRef<LiveProjectionClient | null>(null);
  const [view, setView] = useState<LiveProjectionView>({
    state: "UNAVAILABLE",
    anomalies: [],
    eventCount: 0,
  });

  useEffect(() => {
    let cancelled = false;
    const client = new LiveProjectionClient(store, transport, runId);
    clientRef.current = client;

    // Single source of truth for the React view: re-reads the full client
    // state on every change. Every frame (historical snapshot, live append,
    // gap, stale, transport-down) routes through sync, so the view always
    // reflects the canonical client state exactly once.
    const sync = () =>
      !cancelled &&
      setView({
        state: client.state,
        anomalies: client.anomalies.map((a) => ({ kind: a.kind, message: a.message })),
        eventCount: client.events.length,
        lastError: client.lastError,
      });

    // Every client state change (bootstrap, replay, live frame, gap/stale,
    // transport-down) re-renders the view via this single callback.
    client.onChange = sync;

    // 1) Register the transport status listener EXPLICITLY (F1) and BEFORE
    // bindTransport() so the initial SUBSCRIBED/CHANNEL_ERROR transition is
    // never missed. SUBSCRIBED alone does NOT force LIVE — the client gates LIVE
    // on its durable-history readiness latch.
    client.setStatusListener((_status, state) => {
      if (state === "PROJECTION_UNAVAILABLE") {
        client.state = "PROJECTION_UNAVAILABLE";
        client.lastError = "realtime channel unavailable";
        sync();
      }
    });

    client.bindTransport();

    // 2) Historical catch-up from the durable store (source of truth).
    client
      .bootstrap()
      .then(() => {
        // 3) Post-bootstrap snapshot closes the frame-loss window: any frame
        //    that arrived during bootstrap is already in client state now.
        sync();
      })
      .catch((err) => {
        client.markTransportDown();
        client.lastError = String(err);
        sync();
      });

    return () => {
      cancelled = true;
      client.close();
    };
  }, [runId, store, transport]);

  return view;
}
