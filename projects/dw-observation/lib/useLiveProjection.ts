"use client";

// React binding for the read-only live projection client (M2).
// Mounts the observer against an injected store + transport. The store/transport
// are supplied by the host app (Postgres + Supabase in prod) so this hook stays
// a read-only consumer with no remote mutation.

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

    const sync = () =>
      !cancelled &&
      setView({
        state: client.state,
        anomalies: client.anomalies.map((a) => ({ kind: a.kind, message: a.message })),
        eventCount: client.events.length,
        lastError: client.lastError,
      });

    client.bindTransport();
    client
      .bootstrap()
      .then(sync)
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
