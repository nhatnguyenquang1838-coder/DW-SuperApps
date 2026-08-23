// Server Component (Next.js App Router) — run list.
//
// REAL mode: reads `runs` through the publishable/RLS-compatible server path
// (lib/serverRunRead.readServerRunList). NO fixture fallback: when config is
// missing or the read is denied, the page renders an explicit degraded state.
//
// MOCK mode (OBSERVATORY_DATA_SOURCE=mock): deterministic fixture-backed list
// for offline review — unchanged.

import { readServerRunList } from "@/lib/serverRunRead";
import { listRuns, UNKNOWN } from "@/lib/observatory";

type ListItem = {
  id: string;
  source: string;
  kind: string;
  started: string | null;
};

export default async function RunsPage() {
  const dataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  let items: ListItem[] = [];
  let degraded = false;
  let backend: "supabase_publishable" | "none" | "mock" = "none";

  if (dataSource === "mock") {
    items = listRuns("mock").map((r) => ({
      id: r.runId,
      source: r.sourceSystem,
      kind: "mock",
      started: r.startedAt,
    }));
    backend = "mock";
  } else {
    const res = await readServerRunList();
    if (res.degraded) {
      degraded = true;
      backend = "none";
    } else {
      backend = "supabase_publishable";
      items = res.runs
        .filter((row) => typeof row.run_id === "string" && row.run_id)
        .map((row) => ({
          id: String(row.run_id),
          source:
            typeof row.source_system === "string"
              ? (row.source_system as string)
              : UNKNOWN,
          kind:
            typeof row.run_kind === "string"
              ? (row.run_kind as string)
              : UNKNOWN,
          started:
            typeof row.started_at === "string"
              ? (row.started_at as string)
              : null,
        }));
    }
  }

  return (
    <section>
      <h1 className="mb-1 text-xl font-semibold">Run history</h1>

      {degraded ? (
        <div className="mb-4 rounded-lg border border-edge bg-panel p-4">
          <p className="text-sm text-accent">PROJECTION_UNAVAILABLE</p>
          <p className="mt-1 text-xs text-muted">
            Supabase is not configured or the read was denied (RLS). Real run
            list is unavailable; no fixture fallback.
          </p>
        </div>
      ) : items.length === 0 ? (
        <p className="mb-4 text-sm text-muted">No runs recorded.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((r) => (
            <a
              key={r.id}
              href={`/runs/${encodeURIComponent(r.id)}`}
              className="block rounded-lg border border-edge bg-panel p-4 transition-colors hover:border-accent/60"
            >
              <div className="flex items-center justify-between">
                <span className="code text-sm font-medium">{r.id}</span>
                <span className="rounded bg-edge px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                  {r.source}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div>
                  <dt className="text-muted">Kind</dt>
                  <dd className="code">{r.kind}</dd>
                </div>
                <div>
                  <dt className="text-muted">Started</dt>
                  <dd className="code">{r.started ?? "—"}</dd>
                </div>
              </dl>
            </a>
          ))}
        </div>
      )}

      <div className="mt-6 rounded-lg border border-edge bg-panel p-4">
        <h2 className="text-sm font-semibold text-accent">Simulated visualizations</h2>
        <p className="mt-1 text-xs text-muted">
          Local review-only playground. No real data, no Supabase, no mutations.
        </p>
        <a
          href="/runs/login-epic"
          className="mt-3 inline-block rounded border border-accent/50 bg-accent/10 px-3 py-1.5 text-sm text-accent transition-colors hover:bg-accent/20"
        >
          Open Login Epic GWC Runtime Graph →
        </a>
      </div>

      <p
        data-testid="list-data-source-badge"
        className="mt-6 text-xs font-mono rounded border border-muted px-2 py-1 inline-block"
      >
        data-source: {dataSource} · backend: {backend}
      </p>
    </section>
  );
}
