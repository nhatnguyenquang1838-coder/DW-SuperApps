export default function RootCard({
  runId,
  startedAt,
  lastEventAt,
  eventCount,
  anomalyCount,
}: {
  runId: string;
  startedAt: string | null;
  lastEventAt: string | null;
  eventCount: number;
  anomalyCount: number;
}) {
  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Run RootCard</h1>
        <span className="rounded bg-edge px-2 py-0.5 text-xs text-muted">
          read-only
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted">Run</dt>
          <dd className="code">{runId}</dd>
        </div>
        <div>
          <dt className="text-muted">Started</dt>
          <dd className="code">{startedAt ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted">Last event</dt>
          <dd className="code">{lastEventAt ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted">Events / Anomalies</dt>
          <dd className="code">
            {eventCount} / {anomalyCount}
          </dd>
        </div>
      </dl>
    </div>
  );
}
