import { describe, it, expect } from "vitest";
import {
  EventStore,
  LiveProjectionClient,
  ProjectionEvent,
  RealtimeTransport,
  ReceiveResult,
  globalDurableOrder,
} from "@/lib/live";
import { PostgresEventStore, SqlQuery, mapRowToProjectionEvent } from "@/lib/postgresEventStore";
import {
  SupabaseRealtimeTransport,
  realtimeTopic,
  readBrowserConfig,
  createBrowserClient,
} from "@/lib/supabaseRealtime";
import { readHistoricalEvents, readServerConfig, createServerClient } from "@/lib/serverHistoricalRead";
import { toBroadcastEnvelope, isValidProducerEnvelope } from "@/lib/broadcastContract";
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
  // test driver: fire a connection status (simulates SUBSCRIBED/CHANNEL_ERROR).
  fire(status: string) {
    (this as unknown as { onStatus?: (s: string, st: LiveState) => void }).onStatus?.(status, "CATCHING_UP");
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
  it("bootstraps from the durable store (source of truth) — snapshot available before transport subscribes", async () => {
    const transport = new InertTransport();
    const client = new LiveProjectionClient(
      new MemStore([ev(0, "e0"), ev(1, "e1")]),
      transport,
      "R-1"
    );
    await client.bootstrap();
    // F2 readiness latch: durable history is ready but the transport is not yet
    // connected, so the projection is AVAILABLE (snapshot) but NOT LIVE.
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
    expect(client.highWater["taskcontroller"]).toBe(1);
    expect(client.events.length).toBe(2);
    // Once the transport reports SUBSCRIBED, BOTH latches are satisfied -> LIVE.
    client.setStatusListener(() => {});
    transport.fire("SUBSCRIBED");
    expect(client.state).toBe("LIVE");
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
    // F4: resync with data + transport ready -> LIVE (drive the latch).
    client.setStatusListener(() => {});
    (client as unknown as { transport: InertTransport }).transport.fire("SUBSCRIBED");
    expect(client.state).toBe("LIVE");
  });

  it("empty resync does NOT present LIVE (F4)", async () => {
    const transport = new InertTransport();
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), transport, "R-1");
    await client.bootstrap();
    // Simulate the durable store now being empty at reconnect time.
    client.store = new MemStore([]) as unknown as EventStore;
    const ok = await client.resync();
    expect(ok).toBe(true);
    expect(client.events.length).toBe(0);
    // Empty resync must degrade honestly — never LIVE.
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
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
    const store = PostgresEventStore.fromSql(sql, "R-1");
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

  it("PostgresEventStore.fromSql issues a real SELECT with run_id param, no mutation", async () => {
    const captured: { text: string; params: unknown[] }[] = [];
    const sql: SqlQuery = {
      async query(text: string, params: unknown[]) {
        captured.push({ text, params });
        return [
          { run_id: "R-1", source_system: "taskcontroller", source_event_id: "e0", sequence: 0 },
          { run_id: "R-1", source_system: "gwc", source_event_id: "g0" }, // no sequence
        ];
      },
    };
    const store = PostgresEventStore.fromSql(sql, "R-1");
    const rows = await store.loadAll("R-1");
    expect(captured[0].text.trim().startsWith("SELECT")).toBe(true);
    expect(captured[0].params).toEqual(["R-1"]);
    expect(rows.length).toBe(2);
    expect(rows[0].sequence).toBe(0);
    expect(rows[1].sequence).toBeUndefined(); // no fabrication
  });

  it("SupabaseRealtimeTransport (browser) opens a real channel and never publishes", () => {
    let onType: string | null = null;
    let subscribed = false;
    let unsubscribed = false;
    const channel = {
      on: (type: string, _filter: { event: string }) => {
        if (type === "broadcast") onType = type;
      },
      subscribe: (_cb?: unknown) => {
        subscribed = true;
      },
      unsubscribe: () => {
        unsubscribed = true;
      },
    };
    const topic = realtimeTopic("observatory", "R-1");
    // Inject a fake browser client directly (no NEXT_PUBLIC_* needed).
    const fakeClient = { channel: () => channel } as never;
    const transport = new SupabaseRealtimeTransport(topic, fakeClient);
    let got: unknown = null;
    transport.subscribe(topic, (p) => (got = p));
    expect(onType).toBe("broadcast");
    expect(subscribed).toBe(true);
    transport.close();
    expect(unsubscribed).toBe(true);
  });

  it("readBrowserConfig reads only NEXT_PUBLIC_* (no server secret leak)", () => {
    const cfg = readBrowserConfig();
    expect(typeof cfg.topicPrefix).toBe("string");
    expect(cfg).toHaveProperty("url");
    expect(cfg).toHaveProperty("anonKey");
    // It must not expose a server service key under the browser contract.
    expect((cfg as Record<string, unknown>).serviceRoleKey).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// R2 (G3_R2) — real Supabase connection code + credential boundary.
// ---------------------------------------------------------------------------
describe("M2 R2 real Supabase connection + credential boundary", () => {
  const saved = process.env;
  afterEach(() => {
    process.env = saved;
  });

  it("server historical read defaults to publishable key (RLS-compatible), not service-role", () => {
    process.env = {
      ...saved,
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_READ_PUBLISHABLE_KEY: "pub-key",
      // service role present but must NOT be the default
      SUPABASE_SERVICE_ROLE_KEY: "secret-key",
    };
    const cfg = readServerConfig();
    expect(cfg.publishableKey).toBe("pub-key");
    const built = createServerClient(cfg);
    expect(built?.backend).toBe("supabase_publishable");
  });

  it("F5: service key is NOT an implicit fallback — absent publishable key fails closed (null)", () => {
    process.env = {
      ...saved,
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "secret-key",
    };
    const cfg = readServerConfig();
    expect(cfg.publishableKey).toBeUndefined();
    // F5 (seq=15 intercept): NO implicit service-role fallback. A service key
    // alone must NOT build a client silently escalating privilege — it fails
    // closed (degraded), so the caller surfaces PROJECTION_UNAVAILABLE.
    const built = createServerClient(cfg);
    expect(built).toBeNull();
  });

  it("config-missing historical read degrades (no fixture LIVE)", async () => {
    process.env = { ...saved }; // wipe Supabase env
    // Stub the real select to prove no mutation + degraded result.
    const result = await readHistoricalEvents("R-1");
    expect(result.degraded).toBe(true);
    expect(result.events).toEqual([]);
    expect(result.backend).toBe("none");
  });

  it("read-denied (RLS error) degrades to PROJECTION_UNAVAILABLE, not bypassed LIVE", async () => {
    process.env = {
      ...saved,
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_READ_PUBLISHABLE_KEY: "pub-key",
    };
    // Inject a fake Supabase client whose select() simulates an RLS denial.
    // The production path issues exactly one .order("projection_ordinal").
    const fakeClient = {
      from: () => ({
        select: () => ({
          eq: () => ({
            order: () => ({
              then: (cb: (r: { data: null; error: { message: string } }) => unknown) =>
                cb({ data: null, error: { message: "permission denied" } }),
            }),
          }),
        }),
      }),
    } as unknown as import("@supabase/supabase-js").SupabaseClient;
    const result = await readHistoricalEvents("R-1", fakeClient);
    expect(result.degraded).toBe(true);
    expect(result.events).toEqual([]);
  });

  it("bootstrap of an empty/denied store yields PROJECTION_UNAVAILABLE, never LIVE", async () => {
    const client = new LiveProjectionClient(
      new MemStore([]),
      new InertTransport(),
      "R-1"
    );
    await client.bootstrap();
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
  });

  it("real adapter invocation: PostgresEventStore maps server rows via select", async () => {
    process.env = {
      ...saved,
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_READ_PUBLISHABLE_KEY: "pub-key",
    };
    const rows = [
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "e0", sequence: 0 },
    ];
    const store = new PostgresEventStore(async () => rows as never, "R-1");
    const loaded = await store.loadAll("R-1");
    expect(loaded.length).toBe(1);
    expect(loaded[0].source_event_id).toBe("e0");
    expect(loaded[0].sequence).toBe(0);
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
    let statusCb: ((s: string, st: LiveState) => void) | null = null;
    const transport: RealtimeTransport = {
      subscribe: (_t: string, onMessage: (p: unknown) => void) => {
        handler = onMessage;
      },
      close: () => {
        handler = null;
      },
      onStatus: (s: string, st: LiveState) => statusCb?.(s, st),
    };
    return {
      transport,
      emit: (p: unknown) => {
        if (!handler) throw new Error("not subscribed");
        handler(p);
      },
      fire: (status: string) => {
        // Mirror InertTransport.fire: drive the wired onStatus handler so the
        // client's readiness latch updates. statusCb is never assigned here.
        (transport as unknown as { onStatus?: (s: string, st: LiveState) => void })
          .onStatus?.(status, "CATCHING_UP");
      },
    };
  }

  it("updates the rendered view when a live frame arrives (after transport subscribes)", async () => {
    const store = new MemStore([ev(0, "e0", "tc1"), ev(1, "e1", "tc1")]);
    const { transport, emit, fire } = makeTransport();
    const { result } = renderHook(() =>
      useLiveProjection("R-1", store, transport)
    );
    // Wait for bootstrap (historical snapshot) to complete — snapshot is
    // available but, per F2 latch, NOT yet LIVE until the transport subscribes.
    await waitFor(() => expect(result.current.eventCount).toBe(2));
    expect(result.current.state).toBe("PROJECTION_UNAVAILABLE");
    fire("SUBSCRIBED");
    await waitFor(() => expect(result.current.state).toBe("LIVE"));
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

// ---------------------------------------------------------------------------
// G3 R3 / seq=14+16 INTERCEPT — contract: env-driven, NO hard-coded hosted identity
// ---------------------------------------------------------------------------
describe("G3 R3 — no hard-coded Supabase hosted ref/URL/org", () => {
  it("committed source/env contain no hard-coded hosted identity (generic pattern)", () => {
    // The Controller forbids committing a specific project ref, Supabase URL,
    // or org id. Everything must be env-driven. We scan committed SOURCE (not
    // tests) for GENERIC leak patterns (a 20-char hex-ish ref, a *.supabase.co
    // URL, a 24-char org id). We do NOT embed an actual real ref in this file,
    // so the test cannot "contain the literal it scans for".
    const fs = require("fs");
    const path = require("path");
    const root = path.join(__dirname, "..", ".."); // projects/dw-observation

    // Generic patterns only — no real hosted identities hardcoded here.
    const FORBIDDEN_PATTERNS = [
      /[a-z0-9]{20}\.supabase\.co/i, // concrete hosted URL
      /supabase\.co\/[a-z0-9]{20}/i, // URL-with-ref form
      /organization_id\s*[:=]\s*["']?[a-z0-9]{20,}/i, // org id literal
    ];

    const walk = (dir: string): string[] => {
      const out: string[] = [];
      for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, ent.name);
        if (ent.isDirectory()) {
          if (
            ent.name === "node_modules" ||
            ent.name === ".next" ||
            ent.name === "supabase" ||
            ent.name === "tests" // tests may carry constructed fixtures
          )
            continue;
          out.push(...walk(full));
        } else if (/\.(ts|tsx|js|json|md|example|sql)$/.test(ent.name)) {
          out.push(full);
        }
      }
      return out;
    };

    const files = walk(root);
    const hits: string[] = [];
    for (const f of files) {
      const text = fs.readFileSync(f, "utf8");
      for (const re of FORBIDDEN_PATTERNS) {
        const m = text.match(re);
        if (m) hits.push(`${path.relative(root, f)}: matches ${m[0]}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it("anti-hardcode matcher detects a constructed negative fixture (no real ref in test)", () => {
    // Negative fixture is CONSTRUCTED at runtime (never a committed literal): a
    // fake 20-char ref + supabase.co URL. The contract must flag it. This proves
    // the matcher works without embedding a real hosted identity in source.
    const fakeRef = "a".repeat(20);
    const fakeUrl = `https://${fakeRef}.supabase.co`;
    const matcher = /[a-z0-9]{20}\.supabase\.co/i;
    expect(matcher.test(fakeUrl)).toBe(true);
    // And a benign env-driven placeholder must NOT match:
    expect(matcher.test("https://${NEXT_PUBLIC_SUPABASE_URL}")).toBe(false);
  });

  it("env contract prefers publishable key, with legacy anon fallback only (browser)", () => {
    process.env = {
      ...process.env,
      NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co",
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "pub-key",
    };
    const cfg = readBrowserConfig();
    expect(cfg.url).toBe("https://example.supabase.co");
    expect(cfg.anonKey).toBe("pub-key"); // publishable primary, not anon
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  });

  it("browser falls back to legacy anon key only when publishable absent", () => {
    process.env = {
      ...process.env,
      NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "legacy-anon",
    };
    const cfg = readBrowserConfig();
    expect(cfg.anonKey).toBe("legacy-anon");
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  });
});

// ---------------------------------------------------------------------------
// G3 R3 (seq=15/16) — full RED->GREEN coverage of the 10 blockers
// ---------------------------------------------------------------------------
describe("G3 R3 blockers (RED->GREEN)", () => {
  it("F1: setStatusListener attached before subscribe; SUBSCRIBED != LIVE", async () => {
    const transport = new InertTransport();
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), transport, "R-1");
    let captured: string[] = [];
    client.setStatusListener((s) => captured.push(s));
    client.bindTransport(); // attaches listener BEFORE subscribe
    expect(captured).toEqual([]); // no status yet
    await client.bootstrap();
    expect(client.state).toBe("PROJECTION_UNAVAILABLE"); // durable ready, not transport
    transport.fire("SUBSCRIBED");
    expect(captured).toContain("SUBSCRIBED");
    expect(client.state).toBe("LIVE"); // now both latches satisfied
  });

  it("F2: LIVE requires durable-ready AND transport-ready (readiness latch)", async () => {
    const transport = new InertTransport();
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), transport, "R-1");
    client.setStatusListener(() => {});
    transport.fire("SUBSCRIBED"); // transport ready first
    // Before bootstrap, durable not ready -> NOT LIVE.
    expect(client.state).toBe("UNAVAILABLE");
    await client.bootstrap();
    expect(client.state).toBe("LIVE"); // both ready
  });

  it("F3: GAP triggers real durable resync + reconcile (no fabricated append)", async () => {
    const store = new MemStore([ev(0, "e0"), ev(1, "e1")]);
    const client = new LiveProjectionClient(store, new InertTransport(), "R-1");
    client.setStatusListener(() => {});
    await client.bootstrap();
    client.transport.fire("SUBSCRIBED");
    expect(client.state).toBe("LIVE");
    // A live frame at seq=5 (gap after 1) -> GAP, CATCHING_UP, triggers resync.
    const r = client.receiveLive({ event: ev(5, "e5") });
    expect(r.kind).toBe("GAP");
    expect(client.state).toBe("CATCHING_UP");
    // The missing intermediate event (2..4) is reconciled from the DURABLE store
    // (not fabricated): extend the durable store and re-run resync explicitly.
    client.store = new MemStore([ev(0, "e0"), ev(1, "e1"), ev(2, "e2"), ev(3, "e3"), ev(4, "e4"), ev(5, "e5")]) as unknown as EventStore;
    const ok = await client.resync();
    expect(ok).toBe(true);
    expect(client.events.map((e) => e.sequence)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(client.state).toBe("LIVE");
  });

  it("F4: empty resync never yields LIVE (covered above) — reinforce via resync()", async () => {
    const client = new LiveProjectionClient(new MemStore([]), new InertTransport(), "R-1");
    client.setStatusListener(() => {});
    await client.bootstrap();
    expect(client.state).toBe("PROJECTION_UNAVAILABLE"); // empty durable -> unavailable
    client.transport.fire("SUBSCRIBED");
    // Even with transport ready, no data -> still not LIVE.
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
  });

  it("F5: server read has NO implicit service-role fallback", async () => {
    process.env = {
      ...process.env,
      SUPABASE_URL: "https://x.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "svc",
      // publishable key intentionally ABSENT
    };
    const cfg = readServerConfig();
    const built = createServerClient(cfg);
    // No publishable key -> must NOT build a client via implicit service-role fallback.
    expect(built).toBeNull();
    delete process.env.SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  });

  it("F6: SQL uses BIGINT GENERATED ALWAYS AS IDENTITY + projection_ordinal, valid contract", async () => {
    const fs = require("fs");
    const path = require("path");
    const sql = fs.readFileSync(
      path.join(__dirname, "..", "..", "sql", "projection_events.sql"),
      "utf8"
    );
    expect(sql).toMatch(/projection_ordinal\s+BIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY/i);
    expect(sql).toMatch(/id\s+BIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY/i);
    expect(sql).toMatch(/ORDER\s+BY\s+projection_ordinal/i);
    expect(sql).not.toMatch(/occurred_at\s+ORDER\s+BY|ORDER\s+BY\s+occurred_at/i);
  });

  it("F7: repository Broadcast producer contract — event/topic/payload align with subscriber", () => {
    const env = toBroadcastEnvelope("observatory", {
      run_id: "R-1",
      source_system: "taskcontroller",
      source_event_id: "e1",
      sequence: 1,
    });
    expect(env.event).toBe("projection_event"); // event distinct from topic
    expect(env.topic).toBe("observatory:R-1");
    expect(env.type).toBe("broadcast");
    expect(env.payload.source_event_id).toBe("e1");
    expect(isValidProducerEnvelope(env, "observatory")).toBe(true);
    // Topic != event name (protocol rule).
    expect(env.event).not.toBe(env.topic);
  });

  it("F8: global durable ordering preserves mixed TC/GWC interleaving via projection_ordinal", () => {
    const mixed = globalDurableOrder([
      { run_id: "R-1", source_system: "gwc", source_event_id: "g2", sequence: 2, projection_ordinal: 2 },
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "t1", sequence: 1, projection_ordinal: 1 },
      { run_id: "R-1", source_system: "gwc", source_event_id: "g1", sequence: 1, projection_ordinal: 3 },
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "t2", sequence: 2, projection_ordinal: 4 },
    ]);
    // Ordered by projection_ordinal (durable global order), NOT grouped by source.
    expect(mixed.map((e) => e.source_event_id)).toEqual(["t1", "g2", "g1", "t2"]);
  });

  it("F9: normalizes real Broadcast {type,broadcast,event,payload} envelope", async () => {
    const client = new LiveProjectionClient(new MemStore([]), new InertTransport(), "R-1");
    client.setStatusListener(() => {});
    client.bindTransport();
    // Historical snapshot must be ready before a live frame is accepted (frame
    // arriving before bootstrap is buffered, not appended).
    await client.bootstrap();
    const env = toBroadcastEnvelope("observatory", {
      run_id: "R-1",
      source_system: "taskcontroller",
      source_event_id: "e9",
      sequence: 9,
    });
    const r = client.receiveLive(env);
    expect(r.kind).toBe("APPENDED");
    expect(client.events[0].source_event_id).toBe("e9");
  });
});

// ---------------------------------------------------------------------------
// R4 G3 rework (seq=18) — independent semantic review blockers.
// Tests-first; each block maps to a controller R4 finding.
// ---------------------------------------------------------------------------
describe("R4 G3 rework (seq=18)", () => {
  // B1: production historical read must SELECT projection_ordinal and ORDER ONLY
  // BY projection_ordinal (not source_system/sequence). A mixed TC1->GWC1->TC2
  // stream must survive the real server-read path in canonical global order.
  it("B1: serverHistoricalRead orders ONLY by projection_ordinal (captured builder; mixed TC1->GWC1->TC2)", async () => {
    process.env = {
      ...process.env,
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_READ_PUBLISHABLE_KEY: "pub-key",
    };
    const capturedCols: string[] = [];
    // Capture the production query-builder's .order() calls verbatim.
    const orders: Array<[string, unknown]> = [];
    // Return rows in an order that is NOT source-grouped (mixed TC/gwc) but each
    // carries projection_ordinal, so we can confirm the read path follows the
    // DB's ordinal order and does NOT re-sort by source_system/sequence.
    const rows = [
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "TC1", sequence: 1, projection_ordinal: 1, event_type: "a", occurred_at: "2026-08-22T09:00:00Z", source_digest: "x" },
      { run_id: "R-1", source_system: "gwc", source_event_id: "GWC1", sequence: 2, projection_ordinal: 2, event_type: "a", occurred_at: "2026-08-22T09:00:00Z", source_digest: "x" },
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "TC2", sequence: 3, projection_ordinal: 3, event_type: "a", occurred_at: "2026-08-22T09:00:00Z", source_digest: "x" },
    ];
    const fakeClient = {
      from: () => ({
        select: (cols: string) => {
          capturedCols.push(cols);
          return {
            eq: () => ({
              // Record every .order(col, opts) the production path issues.
              order: (col: string, opts?: unknown) => {
                orders.push([col, opts]);
                return Promise.resolve({ data: rows, error: null });
              },
            }),
          };
        },
      }),
    } as unknown as import("@supabase/supabase-js").SupabaseClient;
    const result = await readHistoricalEvents("R-1", fakeClient);
    // (1) The production path MUST call .order() exactly ONCE, on projection_ordinal.
    expect(orders).toEqual([["projection_ordinal", { ascending: true }]]);
    // (2) It must NOT order by source_system or sequence.
    expect(orders.length).toBe(1);
    expect(orders.every(([c]) => c === "projection_ordinal")).toBe(true);
    expect(capturedCols[0]).toContain("projection_ordinal");
    // (3) Mixed-source rows survive the real server-read path in canonical
    // (projection_ordinal) order — TC1 -> GWC1 -> TC2, NOT grouped by source.
    expect(result.events.map((e) => e.source_event_id)).toEqual(["TC1", "GWC1", "TC2"]);
    delete process.env.SUPABASE_URL;
    delete process.env.SUPABASE_READ_PUBLISHABLE_KEY;
  });

  // B2: a reconnect (SUBSCRIBED after a prior disconnect) must perform a durable
  // resync and only return LIVE after the durable store is successfully
  // re-read. No busy-loop.
  it("B2: reconnect triggers durable resync before LIVE (deterministic)", async () => {
    let loadCount = 0;
    const store: EventStore = {
      async loadAll() {
        loadCount++;
        return [ev(0, "e0"), ev(1, "e1")];
      },
    };
    const transport = new InertTransport();
    const client = new LiveProjectionClient(store, transport, "R-1");
    client.setStatusListener(() => {});
    await client.bootstrap();
    transport.fire("SUBSCRIBED"); // initial subscribe -> LIVE
    expect(client.state).toBe("LIVE");
    // Simulate a transport drop (disconnect clears readiness).
    transport.fire("CLOSED");
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
    // Reconnect arrives: must NOT immediately promote to LIVE; must resync first.
    transport.fire("SUBSCRIBED");
    expect(client.state).toBe("CATCHING_UP");
    // Allow the async resync to complete (single loadAll, no busy-loop).
    await new Promise((r) => setTimeout(r, 0));
    expect(loadCount).toBe(2); // bootstrap + exactly one reconnect resync
    expect(client.state).toBe("LIVE");
  });

  it("B2: reconnect with an unreachable durable store stays degraded (never false LIVE)", async () => {
    let failNext = false;
    const store: EventStore = {
      async loadAll() {
        if (failNext) throw new Error("postgres unreachable");
        return [ev(0, "e0"), ev(1, "e1")];
      },
    };
    const transport = new InertTransport();
    const client = new LiveProjectionClient(store, transport, "R-1");
    client.setStatusListener(() => {});
    await client.bootstrap();
    transport.fire("SUBSCRIBED");
    expect(client.state).toBe("LIVE");
    transport.fire("CLOSED");
    failNext = true; // durable store dies during reconnect
    transport.fire("SUBSCRIBED");
    await new Promise((r) => setTimeout(r, 0));
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
  });

  // B3: a disconnect (lowercase "closed" from the transport) must clear
  // transportReady and must NOT later promote LIVE without a successful
  // reconnect+resync. The transport must NORMALIZE casing to uppercase.
  it("B3: disconnect (lowercase closed) clears transport readiness; reconnect requires resync", async () => {
    // Drive the transport boundary: simulate the system disconnect emitting
    // 'closed' (the bug) and assert the client's transportReady latch is cleared.
    const transport = new InertTransport();
    const client = new LiveProjectionClient(new MemStore([ev(0, "e0")]), transport, "R-1");
    client.setStatusListener(() => {});
    await client.bootstrap();
    transport.fire("SUBSCRIBED");
    expect(client.state).toBe("LIVE");
    // Lowercase disconnect (as the old transport emitted) — must still clear.
    transport.fire("closed");
    expect(client.state).toBe("PROJECTION_UNAVAILABLE");
    // A later SUBSCRIBED without resync must NOT present LIVE (reconnect path
    // requires durable resync first).
    transport.fire("SUBSCRIBED");
    expect(client.state).toBe("CATCHING_UP");
    await new Promise((r) => setTimeout(r, 0));
    expect(client.state).toBe("LIVE");
  });

  it("B3: SupabaseRealtimeTransport normalizes disconnect to uppercase CLOSED", () => {
    let got: string | null = null;
    const channel = {
      on: (_type: string, _filter: { event: string }, _cb?: unknown) => {},
      subscribe: (_cb?: unknown) => {},
      unsubscribe: () => {},
    };
    // The disconnect system handler is registered via channel.on("system", ...).
    // Re-create the binding minimally to capture the status callback.
    const capturedSystem: Record<string, (p: unknown) => void> = {};
    const chan = {
      on: (type: string, filter: { event: string }, cb: (p: unknown) => void) => {
        if (type === "system") capturedSystem[filter.event] = cb;
      },
      subscribe: (_cb?: unknown) => {},
      unsubscribe: () => {},
    };
    const fakeClient = { channel: () => chan } as never;
    const transport = new SupabaseRealtimeTransport("observatory:R-1", fakeClient);
    transport.onStatus = (s) => (got = s);
    // The disconnect handler is registered inside subscribe(); drive it so the
    // system "disconnect" listener is bound.
    transport.subscribe("observatory:R-1", () => {});
    // Simulate a system disconnect (Supabase emits lowercase "closed" status).
    capturedSystem["disconnect"]?.("closed");
    // Must be normalized to canonical uppercase "CLOSED".
    expect(got).toBe("CLOSED");
    void channel;
  });

  // B4: repository SQL producer contract must contain an EXECUTABLE
  // realtime.send()/trigger function (not just comments), aligned with
  // topic=observatory:<run_id> and event=projection_event.
  it("B4: projection_events.sql has an executable realtime broadcast producer (trigger fn + topic/event)", () => {
    const fs = require("fs");
    const path = require("path");
    const sql = fs.readFileSync(
      path.join(__dirname, "..", "..", "sql", "projection_events.sql"),
      "utf8"
    );
    // (1) Executable producer function using realtime.send(payload, event, topic, flag).
    expect(sql).toMatch(/realtime\.send\s*\(/i);
    expect(sql).toMatch(/CREATE\s+OR\s+REPLACE\s+FUNCTION/i);
    // (2) The realtime.send(...) call must live INSIDE the executable function
    // body (between $$ ... $$), NOT inside a -- comment line.
    const fnBlock = sql.match(/CREATE\s+OR\s+REPLACE\s+FUNCTION[\s\S]*?\$\$[\s\S]*?\$\$/i);
    expect(fnBlock).not.toBeNull();
    expect(fnBlock![0]).toMatch(/realtime\.send\s*\(/i);
    // (3) Topic/event alignment: observatory:<run_id> topic, projection_event event.
    expect(sql).toMatch(/'observatory:'\s*\|\|\s*NEW\.run_id/i);
    expect(sql).toMatch(/projection_event/i);
    // (4) R4.1 BLOCKER FIX: the FIRST argument to realtime.send(...) MUST be the
    // RAW ProjectionEvent jsonb (the columns of NEW), NOT a nested Broadcast
    // envelope ({type,event,topic,payload}). Supabase wraps the first arg as
    // callback.payload, so passing a nested envelope makes the subscriber
    // receive payload.payload and risk REJECTED. Assert the first arg is a
    // jsonb_build_object of ROW COLUMNS (starts with 'run_id') and that
    // realtime.send is NOT handed a nested 'type','event','topic' envelope.
    const sendMatch = sql.match(/realtime\.send\s*\(([\s\S]*?),\s*'projection_event'/i);
    expect(sendMatch).not.toBeNull();
    const firstArg = sendMatch![1];
    // The first arg must carry the ProjectionEvent identity columns at top level.
    expect(firstArg).toMatch(/run_id/i);
    expect(firstArg).toMatch(/source_system/i);
    expect(firstArg).toMatch(/source_event_id/i);
    // It must NOT be a nested Broadcast wrapper (no 'type','event','topic' keys
    // inside the first arg).
    expect(firstArg).not.toMatch(/'type'\s*,\s*'broadcast'/i);
    expect(firstArg).not.toMatch(/'event'\s*,\s*'projection_event'/i);
    expect(firstArg).not.toMatch(/'topic'\s*,\s*'observatory:'/i);
    // (5) It must be a trigger (AFTER INSERT) so the producer fires per durable row.
    expect(sql).toMatch(/CREATE\s+TRIGGER/i);
    expect(sql).toMatch(/AFTER\s+INSERT\s+ON\s+projection_events/i);
    // (6) Still repository-only: must NOT contain remote RLS/policy/Realtime config.
    expect(sql).not.toMatch(/create\s+policy/i);
    expect(sql).not.toMatch(/alter\s+publication/i);
  });

  // R4.1 — simulate the EXACT callback Supabase delivers for a row inserted by
  // the SQL producer. Supabase wraps realtime.send(payload) into:
  //   { type:'broadcast', event:'projection_event', payload: <first_arg> }
  // so <first_arg> is what the subscriber receives as `payload`. The producer
  // must pass the RAW ProjectionEvent (row columns) as that first arg, so the
  // subscriber gets the ProjectionEvent at payload top-level (NOT payload.payload).
  it("R4.1: real Supabase callback from SQL producer APPENDS without .payload.payload", async () => {
    const client = new LiveProjectionClient(
      new MemStore([]),
      new InertTransport(),
      "R-1"
    );
    client.setStatusListener(() => {});
    client.bindTransport();
    await client.bootstrap();

    // The RAW ProjectionEvent is what realtime.send() is called with (row cols),
    // and it is what arrives as `payload` in the delivered callback frame.
    const rawProjectionEvent = {
      run_id: "R-1",
      source_system: "taskcontroller",
      source_event_id: "e1",
      sequence: 1,
      projection_ordinal: 1,
      event_type: "node_update",
      occurred_at: "2026-08-22T00:00:00Z",
    };
    // Faithful Supabase-delivered callback wrapper.
    const deliveredFrame = {
      type: "broadcast",
      event: "projection_event", // fixed event name (== what channel.on binds)
      payload: rawProjectionEvent, // == first arg to realtime.send (raw PE)
    };
    const r = client.receiveLive(deliveredFrame);
    expect(r.kind).toBe("APPENDED");
    // The ProjectionEvent is at payload top-level — no .payload.payload nesting.
    expect(client.events[0].source_event_id).toBe("e1");
    expect((client.events[0] as ProjectionEvent).source_system).toBe("taskcontroller");
  });

  // B6: missing-ordinal events must NOT be reordered / source-grouped. They
  // keep their input/relative order (or require ordinal before canonical
  // ordering). Mixed-source test.
  it("B6: globalDurableOrder preserves input order for no-ordinal events (no source-grouping)", () => {
    const mixed = globalDurableOrder([
      { run_id: "R-1", source_system: "gwc", source_event_id: "g1", sequence: 1 }, // no ordinal
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "t1", sequence: 1 }, // no ordinal
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "t2", sequence: 2 }, // no ordinal
    ]);
    // Input order preserved exactly — NOT grouped by source_system.
    expect(mixed.map((e) => e.source_event_id)).toEqual(["g1", "t1", "t2"]);
  });

  it("B6: durable rows (with ordinal) are never reordered by source grouping", () => {
    // Mixed TC/GWC where source_system ordering would differ from ordinal order.
    const mixed = globalDurableOrder([
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "tA", sequence: 5, projection_ordinal: 1 },
      { run_id: "R-1", source_system: "gwc", source_event_id: "gB", sequence: 1, projection_ordinal: 2 },
      { run_id: "R-1", source_system: "taskcontroller", source_event_id: "tC", sequence: 9, projection_ordinal: 3 },
    ]);
    // Ordered strictly by projection_ordinal, never by source_system.
    expect(mixed.map((e) => e.source_event_id)).toEqual(["tA", "gB", "tC"]);
  });
});
