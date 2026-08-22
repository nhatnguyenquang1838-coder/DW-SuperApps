// M2 — browser Supabase Realtime Broadcast subscriber (transport only).
//
// Production wiring for the RealtimeTransport interface (lib/live.ts). This is
// the actual #73 browser binding: it subscribes to a Supabase Realtime channel
// and forwards `broadcast` frames to the observer. It NEVER publishes and
// performs NO remote mutation (Broadcast is transport only, not canonical
// history). The Supabase client is injected so the module stays dependency-free
// and unit-testable; it is a boundary contract, not a live connection here.
//
// Environment contract (host supplies, never committed as secrets):
//   NEXT_PUBLIC_SUPABASE_URL        - Supabase project URL
//   NEXT_PUBLIC_SUPABASE_ANON_KEY   - Supabase anon/public key (read/broadcast)
//   NEXT_PUBLIC_OBSERVATORY_REALTIME_TOPIC_PREFIX (optional) - channel prefix
//
// Usage (host app):
//   const client = createClient(url, anonKey);
//   const channel = client.channel(`observatory:${runId}`);
//   const transport = new SupabaseRealtimeTransport(channel, `observatory:${runId}`);
//   const obs = new LiveProjectionClient(store, transport, runId);
//   await obs.bootstrap();
//   obs.bindTransport();  // listens for broadcast frames

import { RealtimeTransport } from "@/lib/live";

export interface SupabaseRealtimeChannel {
  on: (
    type: "broadcast",
    filter: { event: string },
    cb: (payload: { event?: unknown }) => void
  ) => unknown;
  subscribe?: (cb?: (status: string) => void) => unknown;
  unsubscribe: () => unknown;
}

export interface SupabaseClientLike {
  channel: (topic: string) => SupabaseRealtimeChannel;
}

export function readRealtimeConfig(): {
  url?: string;
  anonKey?: string;
  topicPrefix: string;
} {
  // Read-only env contract. No secrets are embedded; missing values mean the
  // transport stays inert (the observer degrades, never fails).
  return {
    url: (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_SUPABASE_URL) || undefined,
    anonKey:
      (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_SUPABASE_ANON_KEY) || undefined,
    topicPrefix:
      (typeof process !== "undefined" &&
        process.env?.NEXT_PUBLIC_OBSERVATORY_REALTIME_TOPIC_PREFIX) ||
      "observatory",
  };
}

export function realtimeTopic(topicPrefix: string, runId: string): string {
  return `${topicPrefix}:${runId}`;
}

export class SupabaseRealtimeTransport implements RealtimeTransport {
  // Bound channel + topic. `subscribe()` attaches the broadcast listener and
  // (if present) initiates the channel subscription; it never publishes.
  constructor(
    private readonly channel: SupabaseRealtimeChannel,
    private readonly topic: string
  ) {}

  subscribe(_topic: string, onMessage: (payload: unknown) => void): void {
    this.channel.on("broadcast", { event: this.topic }, (payload) =>
      onMessage(payload)
    );
    // Initiate the channel subscription if the binding exposes it. Subscribing
    // does not publish anything; it only begins receiving broadcast frames.
    if (typeof this.channel.subscribe === "function") {
      this.channel.subscribe();
    }
  }

  close(): void {
    try {
      this.channel.unsubscribe();
    } catch {
      // Tearing down must never fail the observer's canonical runtime.
    }
  }
}
