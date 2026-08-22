import { listRuns } from "@/lib/observatory";

export default function RunsPage() {
  const runs = listRuns();
  return (
    <section>
      <h1 className="mb-1 text-xl font-semibold">Run history</h1>
      <p className="mb-4 text-sm text-muted">
        Fixture-backed historical projections from the merged M0 contract.
        Read-only.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {runs.map((r) => (
          <a
            key={r.runId}
            href={`/runs/${encodeURIComponent(r.runId)}`}
            className="block rounded-lg border border-edge bg-panel p-4 transition-colors hover:border-accent/60"
          >
            <div className="flex items-center justify-between">
              <span className="code text-sm font-medium">{r.runId}</span>
              <span className="rounded bg-edge px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                {r.sourceSystem}
              </span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div>
                <dt className="text-muted">Events</dt>
                <dd className="code">{r.eventCount}</dd>
              </div>
              <div>
                <dt className="text-muted">Anomalies</dt>
                <dd className="code">{r.anomalyCount}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted">Gates</dt>
                <dd className="code">
                  {Object.keys(r.gates).join(", ") || "—"}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted">Last event</dt>
                <dd className="code">{r.lastEventAt ?? "—"}</dd>
              </div>
            </dl>
          </a>
        ))}
      </div>
    </section>
  );
}
