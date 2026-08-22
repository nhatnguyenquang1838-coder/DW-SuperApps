// M2 — browser Supabase Realtime Broadcast transport (transport only).
//
// REAL connection code (R2 / G3_R2): uses @supabase/supabase-js directly.
// - The browser Supabase client is constructed here from the public URL +
//   publishable anon key (NEXT_PUBLIC_* — safe to ship to the browser).
// - A real Realtime Broadcast channel is created and subscribed; its lifecycle
//   (SUBSCRIBED / CHANNEL_ERROR / TIMED_OUT / CLOSED) is surfaced to the
//   projection state so the UI reflects connection health.
// - It NEVER publishes and performs NO remote mutation (Broadcast is transport
//   only, not canonical history). The durable store remains the source of truth.
//
// Environment contract (browser-safe, no secrets):
//   NEXT_PUBLIC_SUPABASE_URL                  - Supabase project URL
//   NEXT_PUBLIC_SUPABASE_ANON_KEY             - publishable anon key (read/broadcast)
//   NEXT_PUBLIC_OBSERVATORY_REALTIME_TOPIC_PREFIX (optional) - channel prefix
//
// Server-only secrets (Supabase service role / DB URL) live in a SEPARATE env
// namespace (SUPABASE_SERVICE_ROLE_KEY / DATABASE_URL) and are read ONLY by the
// server historical-read module (lib/serverHistoricalRead.ts) — never imported
// into this browser bundle.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { RealtimeTransport, LiveState } from "@/lib/live";

export type ChannelStatus =
  | "idle"
  | "connecting"
  | "subscribed"
  | "channel_error"
  | "timed_out"
  | "closed";

export interface SupabaseBrowserConfig {
  url?: string;
  anonKey?: string;
  topicPrefix: string;
}

export function readBrowserConfig(): SupabaseBrowserConfig {
  // Browser-safe: only NEXT_PUBLIC_* values. Missing -> transport degrades
  // (no connection attempted; observer stays read-only from snapshot).
  //
  // Env contract (per Controller intercept, seq=14): the PUBLISHABLE key is the
  // primary browser credential; the legacy ANON key is a fallback only. Both
  // are PUBLIC/publishable credentials — safe to ship to the browser. No
  // project ref / URL / org id is ever hard-coded; the URL comes from env too.
  const url =
    (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_SUPABASE_URL) ||
    undefined;
  const publishableKey =
    (typeof process !== "undefined" &&
      process.env?.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) ||
    (typeof process !== "undefined" &&
      process.env?.NEXT_PUBLIC_SUPABASE_ANON_KEY) || // legacy fallback only
    undefined;
  return {
    url,
    anonKey: publishableKey,
    topicPrefix:
      (typeof process !== "undefined" &&
        process.env?.NEXT_PUBLIC_OBSERVATORY_REALTIME_TOPIC_PREFIX) ||
      "observatory",
  };
}

export function realtimeTopic(topicPrefix: string, runId: string): string {
  return `${topicPrefix}:${runId}`;
}

// Thin wrapper around the real Supabase Realtime channel so the transport can
// report connection status to the projection observer.
export interface ObservableChannel {
  on: (
    type: "broadcast" | "system",
    filter: { event: string },
    cb: (payload: unknown) => void
  ) => void;
  subscribe: (cb: (status: ChannelStatus) => void) => void;
  unsubscribe: () => void;
}

// Build a real browser Supabase client. Returns null when browser env is
// absent (caller degrades to inert transport). The client never holds a
// server secret.
export function createBrowserClient(
  cfg: SupabaseBrowserConfig
): SupabaseClient | null {
  if (!cfg.url || !cfg.anonKey) return null;
  return createClient(cfg.url, cfg.anonKey, {
    realtime: { params: { eventsPerSecond: 5 } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

export class SupabaseRealtimeTransport implements RealtimeTransport {
  private channel: ReturnType<SupabaseClient["channel"]> | null = null;
  private client: SupabaseClient | null = null;
  private closed = false;
  // Surfaced to the observer via onStatus so the UI shows connection health.
  status: ChannelStatus = "idle";
  onStatus?: (status: ChannelStatus, state: LiveState) => void;

  // Optional injected client (test seam). When omitted, the real browser client
  // is created from NEXT_PUBLIC_* publishable credentials.
  constructor(private readonly topic: string, private readonly clientOverride?: SupabaseClient) {}

  // Real channel lifecycle: create the browser client, open a Broadcast
  // channel, bind the broadcast listener, and subscribe. Connection status is
  // reported through onStatus so the projection state reflects it.
  subscribe(_topic: string, onMessage: (payload: unknown) => void): void {
    if (this.closed) return;
    const client = this.clientOverride ?? createBrowserClient(readBrowserConfig());
    this.client = client;
    if (!client) {
      // No browser env: stay inert (snapshot-only). Degrade, never fail.
      this.status = "idle";
      this.onStatus?.("idle", "PROJECTION_UNAVAILABLE");
      return;
    }
    this.status = "connecting";
    this.onStatus?.("connecting", "CATCHING_UP");

    const channel = client.channel(this.topic, {
      config: { broadcast: { self: false } },
    });
    this.channel = channel;

    channel.on("broadcast", { event: this.topic }, (payload) =>
      onMessage(payload)
    );
    channel.on("system", { event: "disconnect" }, () => {
      this.status = "closed";
      this.onStatus?.("closed", "PROJECTION_UNAVAILABLE");
    });

    channel.subscribe((status) => {
      // Map the Supabase REALTIME_SUBSCRIBE_STATES (uppercase) onto our
      // lowercase ChannelStatus.
      const map: Record<string, ChannelStatus> = {
        SUBSCRIBED: "subscribed",
        CHANNEL_ERROR: "channel_error",
        TIMED_OUT: "timed_out",
        CLOSED: "closed",
        JOINED: "subscribed",
      };
      const s = map[String(status)] ?? "idle";
      this.status = s;
      if (s === "subscribed") {
        this.onStatus?.("subscribed", "LIVE");
      } else if (s === "channel_error") {
        this.onStatus?.("channel_error", "PROJECTION_UNAVAILABLE");
      } else if (s === "timed_out") {
        this.onStatus?.("timed_out", "PROJECTION_UNAVAILABLE");
      } else if (s === "closed") {
        this.onStatus?.("closed", "PROJECTION_UNAVAILABLE");
      }
    });
  }

  close(): void {
    this.closed = true;
    this.status = "closed";
    try {
      this.channel?.unsubscribe();
      this.client?.removeChannel(this.channel!);
      this.client?.realtime?.disconnect?.();
    } catch {
      // Tearing down must never fail the observer's canonical runtime.
    }
  }
}
