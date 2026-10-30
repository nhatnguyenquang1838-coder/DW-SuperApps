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
        background: "var(--dwo-color-bg-surface)",
        color: "var(--dwo-color-text-primary)",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <style>{`
        .notion-run-card { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-surface); }
        .notion-run-card:hover { border-color: var(--dwo-color-text-primary); }
        .notion-link-btn { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-subtle); color: var(--dwo-color-text-primary); }
        .notion-link-btn:hover { background: var(--dwo-color-bg-canvas); }
      `}</style>
      <div className="mx-auto max-w-5xl px-6 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1
              className="mb-1 text-2xl font-bold tracking-tight"
              style={{ color: "var(--dwo-color-text-primary)" }}
            >
              Run Explorer
            </h1>
            <p className="text-sm" style={{ color: "var(--dwo-color-text-muted)" }}>
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
              borderColor: "var(--dwo-color-state-amber)",
              background: "var(--dwo-color-bg-subtle)",
              color: "var(--dwo-color-state-amber)",
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
                style={{ color: "var(--dwo-color-state-amber)" }}
              >
                /dev/fixtures
              </a>
              .
            </p>
          </div>
        ) : items.length === 0 ? (
          <p className="my-6 text-sm" style={{ color: "var(--dwo-color-text-muted)" }}>
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
                    style={{ color: "var(--dwo-color-text-primary)" }}
                  >
                    {r.id}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: "var(--dwo-color-bg-subtle)", color: "var(--dwo-color-text-muted)" }}
                  >
                    {r.source}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt style={{ color: "var(--dwo-color-text-faint)" }}>Kind</dt>
                    <dd style={{ color: "var(--dwo-color-text-primary)" }}>{r.kind}</dd>
                  </div>
                  <div>
                    <dt style={{ color: "var(--dwo-color-text-faint)" }}>Started</dt>
                    <dd style={{ color: "var(--dwo-color-text-primary)" }}>{r.started ?? "—"}</dd>
                  </div>
                </dl>
              </a>
            ))}
          </div>
        )}

        <p
          data-testid="list-data-source-badge"
          className="mt-6 inline-block rounded border px-2 py-1 font-mono text-xs"
          style={{ borderColor: "var(--dwo-color-border-default)", color: "var(--dwo-color-text-muted)" }}
        >
          data-source: {dataSource} · backend: {backend}
        </p>
      </div>
    </div>
  );
}
