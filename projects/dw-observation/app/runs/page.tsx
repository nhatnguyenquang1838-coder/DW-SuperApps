// Server Component (Next.js App Router) — run list.
//
// REAL mode: reads `runs` through the publishable/RLS-compatible server path
// (lib/serverRunRead.readServerRunList). When Supabase is unavailable, falls
// back to deterministic fixture data so the UI is always usable for review.
//
// MOCK mode (OBSERVATORY_DATA_SOURCE=mock): deterministic fixture-backed list
// for offline review — unchanged.
//
// Notion-style presentation: light background, clean sans-serif typography,
// minimal cards with subtle borders. The page overrides the app's dark body
// background so it reads as a proper light Notion surface.

import { readServerRunList } from "@/lib/serverRunRead";
import { listRuns, UNKNOWN, DataSource } from "@/lib/observatory";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";

type ListItem = {
  id: string;
  source: string;
  kind: string;
  started: string | null;
  lane?: string;
  task?: string;
  controller?: string;
  executor?: string;
  branch?: string;
  next?: string;
  eventCount?: number;
  anomalyCount?: number;
};

function toItems(runs: ReturnType<typeof listRuns>): ListItem[] {
  return runs.map((r) => ({
    id: r.runId,
    source: r.sourceSystem,
    kind: r.lane ?? "run",
    started: r.startedAt,
    lane: r.lane ?? undefined,
    task: r.task ?? undefined,
    controller: r.controller ?? undefined,
    executor: r.executor ?? undefined,
    branch: r.branch ?? undefined,
    next: r.next ?? undefined,
    eventCount: r.eventCount,
    anomalyCount: r.anomalyCount,
  }));
}

export default async function RunsPage() {
  const dataSource: DataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  let items: ListItem[] = [];
  let backend: "supabase_publishable" | "none" | "mock" | "fixture-fallback" = "none";
  let fallbackNotice = false;

  if (dataSource === "mock") {
    items = toItems(listRuns("mock"));
    backend = "mock";
  } else {
    try {
      const res = await readServerRunList();
      if (res.degraded) {
        fallbackNotice = true;
        backend = "fixture-fallback";
        items = toItems(listRuns("mock"));
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
    } catch {
      fallbackNotice = true;
      backend = "fixture-fallback";
      items = toItems(listRuns("mock"));
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
        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: "#37352f" }}
        >
          Run history
        </h1>
        <p className="mb-6 text-sm" style={{ color: "#787774" }}>
          DW Run Observatory — read-only historical projection
        </p>

        {fallbackNotice && (
          <div
            className="mb-6 rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "#f0b429",
              background: "#fdf6e3",
              color: "#8a6d1a",
            }}
          >
            Supabase unavailable — showing fixture data for review. No real
            data, no mutations.
          </div>
        )}

        {items.length === 0 ? (
          <p className="text-sm" style={{ color: "#787774" }}>
            No runs recorded.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  <div>
                    <dt style={{ color: "#9b9a97" }}>Kind</dt>
                    <dd className="code" style={{ color: "#37352f" }}>
                      {r.kind}
                    </dd>
                  </div>
                  <div>
                    <dt style={{ color: "#9b9a97" }}>Started</dt>
                    <dd className="code" style={{ color: "#37352f" }}>
                      {r.started ?? "—"}
                    </dd>
                  </div>
                  {r.lane && (
                    <div>
                      <dt style={{ color: "#9b9a97" }}>Lane</dt>
                      <dd className="code" style={{ color: "#37352f" }}>
                        {r.lane}
                      </dd>
                    </div>
                  )}
                  {r.task && (
                    <div>
                      <dt style={{ color: "#9b9a97" }}>Task</dt>
                      <dd className="code" style={{ color: "#37352f" }}>
                        {r.task}
                      </dd>
                    </div>
                  )}
                  {r.controller && (
                    <div>
                      <dt style={{ color: "#9b9a97" }}>Controller</dt>
                      <dd className="code" style={{ color: "#37352f" }}>
                        {r.controller}
                      </dd>
                    </div>
                  )}
                  {r.executor && (
                    <div>
                      <dt style={{ color: "#9b9a97" }}>Executor</dt>
                      <dd className="code" style={{ color: "#37352f" }}>
                        {r.executor}
                      </dd>
                    </div>
                  )}
                  {r.branch && (
                    <div>
                      <dt style={{ color: "#9b9a97" }}>Branch</dt>
                      <dd className="code" style={{ color: "#37352f" }}>
                        {r.branch}
                      </dd>
                    </div>
                  )}
                  {r.next && (
                    <div>
                      <dt style={{ color: "#9b9a97" }}>Next</dt>
                      <dd className="code" style={{ color: "#37352f" }}>
                        {r.next}
                      </dd>
                    </div>
                  )}
                </dl>
                {(r.eventCount !== undefined ||
                  r.anomalyCount !== undefined) && (
                  <div
                    className="mt-2 flex gap-2 text-[10px]"
                    style={{ color: "#9b9a97" }}
                  >
                    {r.eventCount !== undefined && (
                      <span>{r.eventCount} events</span>
                    )}
                    {r.anomalyCount !== undefined && r.anomalyCount > 0 && (
                      <span style={{ color: "#b54708" }}>
                        {r.anomalyCount} anomalies
                      </span>
                    )}
                  </div>
                )}
              </a>
            ))}
          </div>
        )}

        <div
          className="mt-8 rounded-lg border p-4"
          style={{ borderColor: "#e9e9e7", background: "#ffffff" }}
        >
          <h2 className="text-sm font-semibold" style={{ color: "#37352f" }}>
            Simulated visualizations
          </h2>
          <p className="mt-1 text-xs" style={{ color: "#787774" }}>
            Local review-only playground. No real data, no Supabase, no
            mutations.
          </p>
          <a
                      href="/runs/login-epic"
                      className="notion-link-btn mt-3 inline-block rounded border px-3 py-1.5 text-sm transition-colors"
                    >
                      Open Login Epic GWC Runtime Graph →
                    </a>
        </div>

        <p
          data-testid="list-data-source-badge"
          className="mt-6 inline-block rounded border px-2 py-1 font-mono text-xs"
          style={{ borderColor: "#e9e9e7", color: "#787774" }}
        >
          data-source: {dataSource} · backend: {backend}
        </p>

        {/* 30 fixtures from fixtureSpec.ts */}
        <div className="mt-10 rounded-lg border p-4" style={{ borderColor: "#e9e9e7", background: "#ffffff" }}>
          <h2 className="text-sm font-semibold" style={{ color: "#37352f" }}>
            Fixture catalog — {FIXTURE_CATALOG.length} runs
          </h2>
          <p className="mt-1 text-xs" style={{ color: "#787774" }}>
            DWO-UR-30-V1 materialized pack. 29 conforming + 1 negative (DEV-RUN-020).
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {FIXTURE_CATALOG.map((f) => (
              <div
                key={f.id}
                className="rounded border px-3 py-2 text-xs"
                style={{ borderColor: "#e9e9e7", background: "#ffffff", color: "#37352f" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold" style={{ color: "#37352f" }}>{f.id}</span>
                  <span
                    className="rounded px-1.5 py-0.5 text-[10px] uppercase"
                    style={{ background: f.kind === "NEGATIVE" ? "#fce4e4" : "#f1f1ef", color: f.kind === "NEGATIVE" ? "#b54708" : "#787774" }}
                  >
                    {f.kind}
                  </span>
                </div>
                <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                  <dt style={{ color: "#9b9a97" }}>domain</dt><dd style={{ color: "#37352f" }}>{f.domain}</dd>
                  <dt style={{ color: "#9b9a97" }}>gate</dt><dd style={{ color: "#37352f" }}>{f.gate ?? "—"}</dd>
                  <dt style={{ color: "#9b9a97" }}>runState</dt><dd style={{ color: "#37352f" }}>{f.runState}</dd>
                  <dt style={{ color: "#9b9a97" }}>auth</dt><dd style={{ color: "#37352f" }}>{f.authorityState}</dd>
                  <dt style={{ color: "#9b9a97" }}>purpose</dt><dd style={{ color: "#787774" }}>{f.purpose}</dd>
                </dl>
                {f.children.length > 0 && (
                  <div className="mt-1 text-[10px]" style={{ color: "#9b9a97" }}>children: {f.children.join(", ")}</div>
                )}
                {f.deps.length > 0 && (
                  <div className="text-[10px]" style={{ color: "#9b9a97" }}>deps: {f.deps.join(", ")}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
