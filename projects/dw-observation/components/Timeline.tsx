// Timeline: events rendered in the EXACT order recorded by the projection
// (the reducer preserves supplied order; it does not reorder). Read-only.
export default function Timeline({
  events,
}: {
  events: Array<Record<string, unknown>>;
}) {
  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <h2 className="mb-3 text-base font-semibold">Timeline</h2>
      {events.length === 0 ? (
        <p className="text-sm text-muted">—</p>
      ) : (
        <ol className="space-y-2">
          {events.map((e, i) => (
            <li
              key={`${String(e.source_event_id ?? i)}-${i}`}
              className="rounded border border-edge/60 bg-surface px-3 py-2 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="code text-xs text-muted">
                  #{i} · seq {String(e.sequence ?? "—")}
                </span>
                <span className="rounded bg-edge px-2 py-0.5 text-xs">
                  {(e.event_type as string) ?? "—"}
                </span>
                {e.gate ? (
                  <span className="text-xs text-muted">
                    gate: {(e.gate as string) ?? "—"}
                  </span>
                ) : null}
                <span className="code text-xs text-muted">
                  {(e.occurred_at as string) ?? "—"}
                </span>
              </div>
              {e.summary ? (
                <p className="mt-1 text-sm">{String(e.summary)}</p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
