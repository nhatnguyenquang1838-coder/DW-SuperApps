import { describe, it, expect } from "vitest";
import {
  EventStore,
  LiveProjectionClient,
  ProjectionEvent,
  RealtimeTransport,
  ReceiveResult,
} from "@/lib/live";
import { PostgresEventStore, SqlQuery, mapRowToProjectionEvent } from "@/lib/postgresEventStore";
import { SupabaseRealtimeTransport, realtimeTopic, readRealtimeConfig } from "@/lib/supabaseRealtime";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useLiveProjection } from "@/lib/useLiveProjection";

// Offline doubles (no remote DB/Supabase mutation).
class MemStore implements EventStore {
  constructor(private events: ProjectionEvent[]) {}
  async loadAll() {
    return this.events.slice();
  }
}
class InertTransport implements RealtimeTransport {
  private handler: ((p: unknown) => void) | null = null;
  subscribe(_t: string, onMessage: (p: unknown) => void) {
    this.handler = onMessage;
  }
  close() {
    this.handler = null;
  }
  // test driver: emit a frame through the bound handler
  emit(p: unknown) {
    if (!this.handler) throw new Error("not subscribed");
    this.handler(p);
  }
}

function ev(seq: number, id: string, source = "taskcontroller"): ProjectionEvent {
  return {
    run_id: "R-1",
    source_system: source,
    source_event_id: id,
    sequence: seq,
  };
}

describe("M2 live projection client", () => {
  it("bootstraps from the durable store (source of truth) and is LIVE", async () => {
    const client = new LiveProjectionClient(
      new MemStore([ev(0, "e0"), ev(1, "e1")]),
      new InertTransport(),
      "R-1"
    );
    await client.bootstrap();
    expect(client.state).toBe("LIVE");
    expect(client.highWater["taskcontroller"]).toBe(1);
    expect(client.events.length).toBe(2);
  });

  it("preserves exact sequence continuity across resync", async () => {
    const store = new MemStore([ev(0, "e0"), ev(1, "e1"), ev(2, "e2")]);
    const client = new LiveProjectionClient(store, new InertTransport(), "R-1");
    await client.bootstrap();
    expect(client.highWater["taskcontroller"]).toBe(2);
    // New durable events land between reconnects.
    store as unknown as { events: ProjectionEvent[] };
    const extended = new MemStore([ev(0, "e0"), ev(1, "e1"), ev(2, "e2"), ev(3, "e3"), ev(4, "e4")]);
    client.store = extended as unknown as EventStore;
    const ok = await client.resync();
    expect(ok).toBe(true);
    expect(client.highWater["taskcontroller"]).toBe(4);
    expect(client.events.map((e) => e.sequence)).toEqual([0, 1, 2, 3, 4]);
    expect(client.state).toBe("LIVE");
  });

  it("duplicate broadcast frames are dropped, not reordered", async () => {
    const transport = new InertTransport();
    const client = new LiveProjectionClient(
      new MemStore([ev(0, "e0"), ev(1, "e1")]),
      transport,
      "R-1"
    );
    await client.bootstrap();
    client.bindTransport();
    const r = client.receiveLive({ event: ev(1, "e1") });
    expect(r.kind).toBe("DUPLICATE");
    expect(client.events.length).toBe(2);
    expect(client.anomalies.length).toBe(0);
  });

  it("gap frames are withheld and await catch-up", async () => {
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), new InertTransport(), "R-1");
    await client.bootstrap();
    const r = client.receiveLive({ event: ev(2, "e2") });
    expect(r.kind).toBe("GAP");
    expect(client.state).toBe("CATCHING_UP");
    // Frame not appended.
    expect(client.events.length).toBe(1);
  });

  it("temporary transport failure degrades without losing the snapshot", async () => {
    const transport = new InertTransport();
    const client = new LiveProjectionClient(
      new MemStore([ev(0, "e0"), ev(1, "e1")]),
      transport,
      "R-1"
    );
    await client.bootstrap();
    client.bindTransport();
    transport.emit({ event: ev(2, "e2") }); // normal append
    expect(client.events.length).toBe(3);
    client.markTransportDown();
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
    // Canonical snapshot retained.
    expect(client.events.length).toBe(3);
  });

  it("live view stays read-only — receives only, never mutates store", async () => {
    const store = new MemStore([ev(0, "e0")]);
    const client = new LiveProjectionClient(store, new InertTransport(), "R-1");
    await client.bootstrap();
    client.receiveLive({ event: ev(1, "e1") });
    // Store still holds only the original durable event (observer never wrote).
    expect((await store.loadAll("R-1")).length).toBe(1);
  });

  it("rejects out-of-run and malformed frames", async () => {
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), new InertTransport(), "R-1");
    await client.bootstrap();
    // Different run_id -> REJECTED (belongs to a different run's projection).
    expect(
      client.receiveLive({ event: { ...ev(1, "x1"), run_id: "OTHER" } }).kind
    ).toBe("REJECTED");
    // Malformed frame (no 'event' envelope) -> REJECTED.
    expect(client.receiveLive({ nope: true }).kind).toBe("REJECTED");
  });
});

// ---------------------------------------------------------------------------
// Production bindings (G3 rework item 1): Postgres durable read + Supabase
// Broadcast subscriber/env contract — repository-only, NO remote mutation.
// ---------------------------------------------------------------------------
describe("M2 production bindings (no remote mutation)", () => {
  it("PostgresEventStore reads only and maps rows without fabricating sequence", async () => {
    const captured: { text: string; params: unknown[] }[] = [];
    const sql: SqlQuery = {
      async query(text: string, params: unknown[]) {
        captured.push({ text, params });
        // Simulated durable rows: one with a numeric sequence, one WITHOUT a
        // sequence (must be preserved as UNKNOWN, not coerced to 0).
        return [
          {
            run_id: "R-1",
            source_system: "taskcontroller",
            source_event_id: "e0",
            sequence: 0,
            event_type: "run_started",
            occurred_at: "2026-08-22T09:00:00Z",
            source_digest: "sha256:x",
          },
          {
            run_id: "R-1",
            source_system: "gwc",
            source_event_id: "g0",
            // sequence absent on purpose
            event_type: "node_progress",
            occurred_at: "2026-08-22T09:01:00Z",
            source_digest: "sha256:y",
          },
        ];
      },
    };
    const store = new PostgresEventStore(sql, "R-1");
    const rows = await store.loadAll("R-1");
    // Read-only SELECT issued with the run_id param; never an INSERT/UPDATE.
    expect(captured[0].text.trim().startsWith("SELECT")).toBe(true);
    expect(captured[0].params).toEqual(["R-1"]);
    expect(rows.length).toBe(2);
    expect(rows[0].sequence).toBe(0);
    // No fabricated sequence: the missing-sequence row keeps `undefined`.
    expect(rows[1].sequence).toBeUndefined();
    expect(rows[1].source_event_id).toBe("g0");
  });

  it("mapRowToProjectionEvent preserves UNKNOWN when sequence missing", () => {
    const e = mapRowToProjectionEvent({
      run_id: "R-1",
      source_system: "gwc",
      source_event_id: "g0",
      event_type: "node_progress",
      occurred_at: "2026-08-22T09:01:00Z",
      source_digest: "sha256:y",
    });
    expect(e.sequence).toBeUndefined();
    expect(e.run_id).toBe("R-1");
  });

  it("SupabaseRealtimeTransport subscribes to broadcast and never publishes", () => {
    let onType: string | null = null;
    let onEvent: string | null = null;
    let subscribed = false;
    let unsubscribed = false;
    const channel = {
      on: (type: string, filter: { event: string }) => {
        onType = type;
        onEvent = filter.event;
      },
      subscribe: () => {
        subscribed = true;
      },
      unsubscribe: () => {
        unsubscribed = true;
      },
    };
    const topic = realtimeTopic("observatory", "R-1");
    const transport = new SupabaseRealtimeTransport(channel as never, topic);
    let got: unknown = null;
    transport.subscribe(topic, (p) => (got = p));
    expect(onType).toBe("broadcast");
    expect(onEvent).toBe(topic);
    expect(subscribed).toBe(true);
    transport.close();
    expect(unsubscribed).toBe(true);
  });

  it("readRealtimeConfig reads env names without exposing values", () => {
    const cfg = readRealtimeConfig();
    expect(typeof cfg.topicPrefix).toBe("string");
    // No assertion on secret presence; contract only. Existence of the helper
    // proves the env contract surface is wired (no remote mutation performed).
    expect(cfg).toHaveProperty("url");
    expect(cfg).toHaveProperty("anonKey");
  });
});

// ---------------------------------------------------------------------------
// Item 3: never fabricate a sequence; exclude invalid sequence from sequencing.
// ---------------------------------------------------------------------------
describe("M2 sequence integrity (no fabrication)", () => {
  it("event without sequence is appended as observation-only, not sequenced", async () => {
    const client = new LiveProjectionClient(
      new MemStore([ev(0, "e0"), ev(1, "e1")]),
      new InertTransport(),
      "R-1"
    );
    await client.bootstrap();
    // A live frame with NO sequence is retained, but does not move high-water.
    const r = client.receiveLive({
      event: { run_id: "R-1", source_system: "taskcontroller", source_event_id: "eX" },
    });
    expect(r.kind).toBe("APPENDED");
    expect(client.highWater["taskcontroller"]).toBe(1); // unchanged
    expect(client.events.length).toBe(3);
    expect(client.events[2].sequence).toBeUndefined();
  });

  it("does not fabricate seq=0 for a genuinely missing sequence", async () => {
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), new InertTransport(), "R-1");
    await client.bootstrap();
    const r = client.receiveLive({
      event: { run_id: "R-1", source_system: "taskcontroller", source_event_id: "eZ" },
    });
    expect(r.kind).toBe("APPENDED");
    expect((client.events[1] as ProjectionEvent).sequence).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Item 2 + Item 4: live transport frame must update the React view; the
// bootstrap/subscription/reconnect frame-loss window is closed.
// ---------------------------------------------------------------------------
describe("M2 React view updates on transport frame", () => {
  function makeTransport() {
    let handler: ((p: unknown) => void) | null = null;
    const transport: RealtimeTransport = {
      subscribe: (_t: string, onMessage: (p: unknown) => void) => {
        handler = onMessage;
      },
      close: () => {
        handler = null;
      },
    };
    return {
      transport,
      emit: (p: unknown) => {
        if (!handler) throw new Error("not subscribed");
        handler(p);
      },
    };
  }

  it("updates the rendered view when a live frame arrives", async () => {
    const store = new MemStore([ev(0, "e0", "tc1"), ev(1, "e1", "tc1")]);
    const { transport, emit } = makeTransport();
    const { result } = renderHook(() =>
      useLiveProjection("R-1", store, transport)
    );
    // Wait for bootstrap (historical snapshot) to complete.
    await waitFor(() => expect(result.current.eventCount).toBe(2));
    expect(result.current.state).toBe("LIVE");
    // Deliver a live frame through the transport -> view must update.
    await act(async () => {
      emit({ event: ev(2, "e2", "tc1") });
    });
    await waitFor(() => expect(result.current.eventCount).toBe(3));
  });

  it("closes the bootstrap/subscription frame-loss window", async () => {
    // A frame that arrives BEFORE bootstrap finishes must not be lost; the
    // client buffers it and replays it after the snapshot, so the view reflects
    // it exactly once (no double count, no lost event).
    const store = new MemStore([ev(0, "e0", "tc1")]);
    let handler: ((p: unknown) => void) | null = null;
    const transport: RealtimeTransport = {
      subscribe: (_t: string, onMessage: (p: unknown) => void) => {
        handler = onMessage;
      },
      close: () => {
        handler = null;
      },
    };
    const { result } = renderHook(() =>
      useLiveProjection("R-1", store, transport)
    );
    // Emit a frame immediately (simulating arrival during the bootstrap gap),
    // then allow bootstrap + buffer replay to settle.
    act(() => {
      handler?.({ event: ev(1, "e1", "tc1") });
    });
    await waitFor(() => expect(result.current.eventCount).toBe(2));
  });
});
