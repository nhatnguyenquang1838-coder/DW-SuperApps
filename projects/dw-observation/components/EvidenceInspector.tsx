// Evidence inspector: surfaces explicit anomaly records and per-event
// evidence_refs. Unknown/missing values are rendered explicitly, never inferred.
export default function EvidenceInspector({
  events,
  anomalies,
  unknownSentinel,
}: {
  events: Array<Record<string, unknown>>;
  anomalies: Array<Record<string, unknown>>;
  unknownSentinel: string;
}) {
  const eventsWithEvidence = events.filter(
    (e) => Array.isArray(e.evidence_refs) && (e.evidence_refs as unknown[]).length > 0
  );

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <h2 className="mb-3 text-base font-semibold">Evidence inspector</h2>

      <h3 className="mb-1 text-sm text-muted">Anomalies (explicit)</h3>
      {anomalies.length === 0 ? (
        <p className="mb-3 text-sm text-muted">{unknownSentinel}</p>
      ) : (
        <ul className="mb-4 space-y-1">
          {anomalies.map((a, i) => (
            <li
              key={i}
              className="rounded border border-edge/60 bg-surface px-3 py-1.5 text-sm"
            >
              <span className="font-medium text-accent">
                {(a.kind as string) ?? unknownSentinel}
              </span>
              {typeof a.at_index === "number" ? (
                <span className="ml-2 text-xs text-muted">@index {a.at_index}</span>
              ) : null}
              {a.message ? (
                <span className="ml-2 text-xs text-muted">
                  {String(a.message)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <h3 className="mb-1 text-sm text-muted">Events with evidence refs</h3>
      {eventsWithEvidence.length === 0 ? (
        <p className="text-sm text-muted">{unknownSentinel}</p>
      ) : (
        <ul className="space-y-1">
          {eventsWithEvidence.map((e, i) => (
            <li
              key={i}
              className="rounded border border-edge/60 bg-surface px-3 py-1.5 text-sm"
            >
              <span className="code text-xs">
                {(e.source_event_id as string) ?? unknownSentinel}
              </span>
              <span className="ml-2 text-xs text-muted">
                refs:{" "}
                {((e.evidence_refs as unknown[]) ?? [])
                  .map((r) => (typeof r === "string" ? r : JSON.stringify(r)))
                  .join(", ") || unknownSentinel}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
