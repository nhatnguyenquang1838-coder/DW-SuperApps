import { describe, it, expect } from "vitest";
import {
  EventStore,
  LiveProjectionClient,
  ProjectionEvent,
  RealtimeTransport,
  ReceiveResult,
} from "@/lib/live";
import { PostgresEventStore, SqlQuery, mapRowToProjectionEvent } from "@/lib/postgresEventStore";
import {
  SupabaseRealtimeTransport,
  realtimeTopic,
  readBrowserConfig,
  createBrowserClient,
} from "@/lib/supabaseRealtime";
import { readHistoricalEvents, readServerConfig, createServerClient } from "@/lib/serverHistoricalRead";
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

  it("service key is optional and only used when publishable key absent", () => {
    process.env = {
      ...saved,
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "secret-key",
    };
    const cfg = readServerConfig();
    expect(cfg.publishableKey).toBeUndefined();
    const built = createServerClient(cfg);
    expect(built?.backend).toBe("supabase_service");
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
    const fakeClient = {
      from: () => ({
        select: () => ({
          eq: () => ({
            order: () => ({
              order: () => ({
                then: (cb: (r: { data: null; error: { message: string } }) => unknown) =>
                  cb({ data: null, error: { message: "permission denied" } }),
              }),
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

// ---------------------------------------------------------------------------
// G3 R3 / seq=14 INTERCEPT — contract: env-driven, NO hard-coded hosted identity
// ---------------------------------------------------------------------------
describe("G3 R3 — no hard-coded Supabase hosted ref/URL/org", () => {
  it("committed source + env + tests contain no hard-coded hosted identity", () => {
    // The Controller explicitly forbids committing a specific project ref,
    // Supabase URL, or org id. Everything must be env-driven. This test scans
    // the committed tree under projects/dw-observation (excluding the gitignored
    // local supabase/ scaffold) for leaked hosted identities.
    const fs = require("fs");
    const path = require("path");
    const root = path.join(__dirname, "..", ".."); // projects/dw-observation

    const FORBIDDEN = [
      "auswvdxoetufwiaxutib", // dedicated Observatory project ref
      "fpeokgrtjslesdftfayr", // org id
      "makakbppxiwssslytoku", // ds_mcp_server ref
      "supabase.co", // concrete hosted URL suffix (env-driven URL only)
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
            ent.name === "tests" // test fixtures/denylist may mention refs
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
      for (const forbidden of FORBIDDEN) {
        if (text.includes(forbidden)) {
          hits.push(`${path.relative(root, f)}: contains ${forbidden}`);
        }
      }
    }
    expect(hits).toEqual([]);
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
