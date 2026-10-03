// Server Component (Next.js App Router) — Run Explorer.
//
// REAL mode: reads `runs` through the publishable/RLS-compatible server path
// (lib/serverRunRead.readServerRunList). When the backend is unavailable or
// the read is denied (RLS), the page renders DEGRADED/PROJECTION_UNAVAILABLE
// — NO silent fixture fallback (fail-closed per CR-826 review).
//
// MOCK mode (OBSERVATORY_DATA_SOURCE=mock): deterministic fixture-backed
// list for offline review. Fixture-only surfaces (30-fixture catalog, sim)
// live under /dev/fixtures and /dev/sim respectively.
//
// Notion-style presentation: light background, clean sans-serif typography,
// minimal cards with subtle borders.

import { readServerRunList } from "@/lib/serverRunRead";
import { listRuns, UNKNOWN, DataSource } from "@/lib/observatory";

type ListItem = {
  id: string;
  source: string;
  kind: string;
  started: string | null;
};

export default async function RunsPage() {
  const dataSource: DataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  let items: ListItem[] = [];
  let backend:
    | "supabase_publishable"
    | "none"
    | "mock"
    | "fixture-fallback" = "none";
  let degraded = false;

  if (dataSource === "mock") {
    items = listRuns("mock").map((r) => ({
      id: r.runId,
      source: r.sourceSystem,
      kind: r.lane ?? "run",
      started: r.startedAt,
    }));
    backend = "mock";
  } else {
    // REAL mode — fail-closed. No fixture fallback.
    try {
      const res = await readServerRunList();
      if (res.degraded) {
        degraded = true;
        backend = "none";
      } else {
        backend = "supabase_publishable";
        items = res.runs
          .filter((row) => typeof row.run_id === "string" && row.run_id)
          .map((row) => {
            const r = row as Record<string, unknown>;
            return {
              id: String(r.run_id),
              source:
                typeof r.source_system === "string"
                  ? (r.source_system as string)
                  : UNKNOWN,
              kind:
                typeof r.run_kind === "string"
                  ? (r.run_kind as string)
                  : UNKNOWN,
              started:
                typeof r.started_at === "string"
                  ? (r.started_at as string)
                  : null,
            };
          });
      }
    } catch {
      degraded = true;
      backend = "none";
    }
  }

  return (
    <div
      className="min-h-screen"
      style={{
        background: "#ffffff",
        color: "#37352f",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <style>{`
        .notion-run-card { border-color: #e9e9e7; background: #ffffff; }
        .notion-run-card:hover { border-color: #37352f; }
        .notion-link-btn { border-color: #d3d1cb; background: #f7f7f5; color: #37352f; }
        .notion-link-btn:hover { background: #efefed; }
      `}</style>
      <div className="mx-auto max-w-5xl px-6 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1
              className="mb-1 text-2xl font-bold tracking-tight"
              style={{ color: "#37352f" }}
            >
              Run Explorer
            </h1>
            <p className="text-sm" style={{ color: "#787774" }}>
              Global run history — read-only historical projection
            </p>
          </div>
          <a
            href="/tasks"
            className="notion-link-btn rounded border px-3 py-1.5 text-sm"
          >
            ← Tasks
          </a>
        </div>

        {degraded ? (
          <div
            className="my-6 rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "#f0b429",
              background: "#fdf6e3",
              color: "#8a6d1a",
            }}
          >
            <p className="font-semibold">DEGRADED / PROJECTION_UNAVAILABLE</p>
            <p className="mt-1 text-xs">
              Supabase is not configured or the read was denied (RLS). Real run
              list is unavailable. To review local data, run with{" "}
              <code className="font-mono">OBSERVATORY_DATA_SOURCE=mock</code> or
              visit{" "}
              <a
                href="/dev/fixtures"
                className="underline"
                style={{ color: "#8a6d1a" }}
              >
                /dev/fixtures
              </a>
              .
            </p>
          </div>
        ) : items.length === 0 ? (
          <p className="my-6 text-sm" style={{ color: "#787774" }}>
            No runs recorded.
          </p>
        ) : (
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((r) => (
              <a
                key={r.id}
                href={`/runs/${encodeURIComponent(r.id)}`}
                className="notion-run-card block rounded-lg border p-4 transition-colors"
                style={{ color: "inherit" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-sm font-semibold"
                    style={{ color: "#37352f" }}
                  >
                    {r.id}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: "#f1f1ef", color: "#787774" }}
                  >
                    {r.source}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt style={{ color: "#9b9a97" }}>Kind</dt>
                    <dd style={{ color: "#37352f" }}>{r.kind}</dd>
                  </div>
                  <div>
                    <dt style={{ color: "#9b9a97" }}>Started</dt>
                    <dd style={{ color: "#37352f" }}>{r.started ?? "—"}</dd>
                  </div>
                </dl>
              </a>
            ))}
          </div>
        )}

        <p
          data-testid="list-data-source-badge"
          className="mt-6 inline-block rounded border px-2 py-1 font-mono text-xs"
          style={{ borderColor: "#e9e9e7", color: "#787774" }}
        >
          data-source: {dataSource} · backend: {backend}
        </p>
      </div>
    </div>
  );
}
