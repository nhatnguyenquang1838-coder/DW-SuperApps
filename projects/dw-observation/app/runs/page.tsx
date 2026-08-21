import { listRuns } from "@/lib/observatory";

export default function RunsPage() {
  const runs = listRuns();
  return (
    <section>
      <h1 className="mb-1 text-xl font-semibold">Run history</h1>
      <p className="mb-4 text-sm text-muted">
        Fixture-backed historical projections from the merged M0 contract. Read-only.
      </p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-edge text-left text-muted">
            <th className="py-2 pr-4">Run</th>
            <th className="py-2 pr-4">Source</th>
            <th className="py-2 pr-4">Started</th>
            <th className="py-2 pr-4">Last event</th>
            <th className="py-2 pr-4">Events</th>
            <th className="py-2 pr-4">Anomalies</th>
            <th className="py-2 pr-4">Gates</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.runId} className="border-b border-edge/50">
              <td className="py-2 pr-4">
                <a className="code" href={`/runs/${encodeURIComponent(r.runId)}`}>
                  {r.runId}
                </a>
              </td>
              <td className="py-2 pr-4">{r.sourceSystem}</td>
              <td className="py-2 pr-4 code">{r.startedAt ?? "—"}</td>
              <td className="py-2 pr-4 code">{r.lastEventAt ?? "—"}</td>
              <td className="py-2 pr-4">{r.eventCount}</td>
              <td className="py-2 pr-4">{r.anomalyCount}</td>
              <td className="py-2 pr-4">
                {Object.keys(r.gates).join(", ") || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
