/**
 * serverRunRead.test.ts
 * TASK 3 RED — contract test for the approved server read adapter:
 *   projects/dw-observation/lib/serverRunRead.ts
 *
 * The adapter (GREEN) reads real Supabase `runs`, `run_gates`, `run_nodes`
 * and `projection_events` via the publishable/anon key boundary and NEVER
 * falls back to fixtures. This file is RED while the module does not exist
 * (presence check fails = missing implementation) and must go GREEN once the
 * adapter is implemented to satisfy exactly these contracts.
 *
 * The module is loaded dynamically through its absolute path (not the `@/`
 * alias) so Vite does not try to resolve a not-yet-existing module at collect
 * time; every contract test reports a clear missing-implementation RED.
 *
 * No network / live Supabase. Uses clientOverrides (mock clients) as test seams.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { ProjectionEvent } from "@/lib/live";
import { getMockProjectionEvents, MOCK_BACKEND } from "@/lib/mockDataSource";

// Vitest runs with cwd = project root (vitest.config.ts root), so the adapter
// path resolves deterministically from the project root. Avoids relying on
// import.meta.url (not a file: scheme under the vitest transform).
const ADAPTER_PATH = resolve(process.cwd(), "lib/serverRunRead.ts");

async function loadAdapter(): Promise<Record<string, unknown>> {
  if (!existsSync(ADAPTER_PATH)) {
    throw new Error(
      "TASK 3 RED: lib/serverRunRead.ts is not implemented yet (missing adapter module)",
    );
  }
  // Dynamic import of the absolute path (works once the file exists in GREEN).
  return import(/* @vite-ignore */ ADAPTER_PATH);
}

// ---------------------------------------------------------------------------
// Mock Supabase client shape (contract for the GREEN adapter's clientOverride).
// ---------------------------------------------------------------------------
type Row = Record<string, unknown>;
type Op = { table: string; op: string; cols?: string };

function makeClient(
  tables: Record<string, { data: Row[] | null; error: unknown | null }>,
  calls: Op[],
): Record<string, unknown> {
  const tableHandler = (table: string) => {
    const t = tables[table] ?? { data: [], error: null };
    return {
      select: (cols: string) => {
        calls.push({ table, op: "select", cols });
        // Model the real Supabase PostgrestFilterBuilder: a thenable builder
        // that also exposes .eq()/.order()/.limit()/.maybeSingle(). This is a
        // harness-fidelity fix (the earlier draft only returned {eq}) so
        // production code can use natural query shapes; assertions unchanged.
        const read = async () => ({ data: t.data, error: t.error });
        const maybeSingle = async () => ({
          data: Array.isArray(t.data) ? (t.data[0] ?? null) : null,
          error: t.error,
        });
        return {
          eq: () => ({ order: read, maybeSingle }),
          order: read,
          limit: read,
          maybeSingle,
          then: (resolve: (v: { data: Row[] | null; error: unknown }) => void) =>
            resolve({ data: t.data, error: t.error }),
        };
      },
      insert: () => {
        calls.push({ table, op: "insert" });
        return Promise.resolve({ data: null, error: null });
      },
      update: () => {
        calls.push({ table, op: "update" });
        return Promise.resolve({ data: null, error: null });
      },
      delete: () => {
        calls.push({ table, op: "delete" });
        return Promise.resolve({ data: null, error: null });
      },
    };
  };
  return { from: (table: string) => tableHandler(table) };
}

// ---------------------------------------------------------------------------
// Task 3 RED contract — every contract test fails with a clear
// missing-implementation error until GREEN creates lib/serverRunRead.ts.
// ---------------------------------------------------------------------------
describe("serverRunRead — Task 3 RED contract", () => {
  it("missing Supabase config returns degraded result and does NOT fall back to fixtures", async () => {
    const mod = await loadAdapter();
    const detail = await (
      mod.readServerRunDetail as (
        runId: string,
        client?: unknown,
      ) => Promise<{
        degraded: boolean;
        backend: string;
        canonicalHistoryAvailable: boolean;
        projectionStatus: string;
        events: unknown[];
        run: unknown;
      }>
    )("DW-OBS-M0-20260821-R2");
    expect(detail.degraded).toBe(true);
    expect(detail.backend).toBe("none");
    expect(detail.canonicalHistoryAvailable).toBe(false);
    expect(detail.projectionStatus).toBe("PROJECTION_UNAVAILABLE");
    // No fixture fallback: even though a fixture exists for this run, the real
    // read must surface PROJECTION_UNAVAILABLE rather than fixture events.
    expect(detail.events).toEqual([]);
  });

  it("RLS denial degrades the read and never falls back to fixtures", async () => {
    const mod = await loadAdapter();
    const calls: Op[] = [];
    const client = makeClient(
      {
        runs: {
          data: null,
          error: { message: "RLS: permission denied for table runs" },
        },
      },
      calls,
    );
    const detail = await (
      mod.readServerRunDetail as (
        runId: string,
        client?: unknown,
      ) => Promise<{
        degraded: boolean;
        canonicalHistoryAvailable: boolean;
        projectionStatus: string;
        events: unknown[];
        run: unknown;
      }>
    )("DW-OBS-M0-20260821-R2", client);
    expect(detail.degraded).toBe(true);
    expect(detail.canonicalHistoryAvailable).toBe(false);
    expect(detail.projectionStatus).toBe("PROJECTION_UNAVAILABLE");
    expect(detail.events).toEqual([]);
    expect(detail.run).toBeNull();
  });

  it("list read path reads `runs` read-only (select only, no writes)", async () => {
    const mod = await loadAdapter();
    const calls: Op[] = [];
    const client = makeClient(
      {
        runs: {
          data: [
            {
              run_id: "RUN-1",
              run_kind: "observed_real",
              source_system: "taskcontroller",
            },
          ],
          error: null,
        },
      },
      calls,
    );
    const list = await (
      mod.readServerRunList as (client?: unknown) => Promise<{
        degraded: boolean;
        runs: Row[];
      }>
    )(client);
    expect(list.degraded).toBe(false);
    expect(list.runs.length).toBe(1);
    // Only read operations against `runs`; no INSERT/UPDATE/DELETE.
    expect(calls.every((c) => c.table === "runs")).toBe(true);
    expect(calls.every((c) => c.op === "select")).toBe(true);
  });

  it("detail read path returns EXACT stored runs, run_gates, run_nodes values", async () => {
    const mod = await loadAdapter();
    const calls: Op[] = [];
    const client = makeClient(
      {
        runs: {
          data: [
            {
              run_id: "RUN-1",
              run_kind: "observed_real",
              source_system: "taskcontroller",
              head_sha: "abc123",
              branch: "main",
            },
          ],
          error: null,
        },
        run_gates: {
          data: [
            {
              gate_id: "G1",
              run_id: "RUN-1",
              gate_label: "G1",
              state: "PASS",
            },
          ],
          error: null,
        },
        run_nodes: {
          data: [
            {
              node_id: "N1",
              run_id: "RUN-1",
              gate_id: "G1",
              state: "COMPLETE",
              label: "M0",
            },
          ],
          error: null,
        },
        projection_events: { data: [], error: null },
      },
      calls,
    );
    const detail = await (
      mod.readServerRunDetail as (
        runId: string,
        client?: unknown,
      ) => Promise<{
        degraded: boolean;
        run: Row | null;
        gates: Row[];
        nodes: Row[];
      }>
    )("RUN-1", client);
    expect(detail.degraded).toBe(false);
    expect(detail.run).toEqual({
      run_id: "RUN-1",
      run_kind: "observed_real",
      source_system: "taskcontroller",
      head_sha: "abc123",
      branch: "main",
    });
    expect(detail.gates).toEqual([
      { gate_id: "G1", run_id: "RUN-1", gate_label: "G1", state: "PASS" },
    ]);
    expect(detail.nodes).toEqual([
      {
        node_id: "N1",
        run_id: "RUN-1",
        gate_id: "G1",
        state: "COMPLETE",
        label: "M0",
      },
    ]);
  });

  it("reconstructed historical run with empty projection_events -> canonicalHistoryAvailable=false / PROJECTION_UNAVAILABLE", async () => {
    const mod = await loadAdapter();
    const calls: Op[] = [];
    const client = makeClient(
      {
        runs: {
          data: [
            {
              run_id: "RUN-HIST",
              run_kind: "reconstructed_history",
              source_system: "taskcontroller",
              reconstruction_basis: "golden_fixture",
            },
          ],
          error: null,
        },
        run_gates: { data: [], error: null },
        run_nodes: { data: [], error: null },
        projection_events: { data: [], error: null },
      },
      calls,
    );
    const detail = await (
      mod.readServerRunDetail as (
        runId: string,
        client?: unknown,
      ) => Promise<{
        run: Row | null;
        canonicalHistoryAvailable: boolean;
        projectionStatus: string;
        events: unknown[];
      }>
    )("RUN-HIST", client);
    expect(detail.run?.run_kind).toBe("reconstructed_history");
    expect(detail.canonicalHistoryAvailable).toBe(false);
    expect(detail.projectionStatus).toBe("PROJECTION_UNAVAILABLE");
    expect(detail.events).toEqual([]);
  });

  it("mock mode behavior remains unchanged (mockDataSource intact)", () => {
    // This test does NOT depend on serverRunRead — it asserts the pre-existing
    // mock data source still works so GREEN cannot break mock mode.
    const runId = "DW-OBS-M0-20260821-R2";
    const events = getMockProjectionEvents(runId);
    expect(events.length).toBeGreaterThan(0);
    expect(events.every((e: ProjectionEvent) => e.run_id === runId)).toBe(true);
    expect(MOCK_BACKEND).toBe("mock");
  });
});
