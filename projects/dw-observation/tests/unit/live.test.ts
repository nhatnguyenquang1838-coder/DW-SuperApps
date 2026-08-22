import { describe, it, expect } from "vitest";
import {
  EventStore,
  LiveProjectionClient,
  ProjectionEvent,
  RealtimeTransport,
} from "@/lib/live";

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
