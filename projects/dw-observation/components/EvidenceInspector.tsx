import { NormalizedEvent } from "@/lib/observatory";

type Props = {
  events: NormalizedEvent[];
  anomalies: Array<Record<string, unknown>>;
  unknownSentinel: string;
};

function JsonView({ value, unknownSentinel }: { value: unknown; unknownSentinel: string }) {
  const text =
    value && typeof value === "object" && Object.keys(value as object).length > 0
      ? JSON.stringify(value, null, 2)
      : unknownSentinel;
  return <pre className="code mt-1 whitespace-pre-wrap text-xs text-muted">{text}</pre>;
}

// G3 correction #3: Evidence Inspector provenance. Renders per-event
// before/after, source_event_id, source_digest, evidence_refs, authority_ref,
// and explicit links when present. Absent values stay explicit (UNKNOWN).
export default function EvidenceInspector({ events, anomalies, unknownSentinel }: Props) {
  const withEvidence = events.filter((e) => e.evidenceRefs.length > 0);

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
                {typeof a.kind === "string" ? (a.kind as string) : unknownSentinel}
              </span>
              {typeof a.at_index === "number" ? (
                <span className="ml-2 text-xs text-muted">@index {a.at_index}</span>
              ) : null}
              {typeof a.message === "string" ? (
                <span className="ml-2 text-xs text-muted">{a.message}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <h3 className="mb-1 text-sm text-muted">Per-event provenance</h3>
      {events.length === 0 ? (
        <p className="text-sm text-muted">{unknownSentinel}</p>
      ) : (
        <ul className="space-y-3">
          {events.map((e, i) => (
            <li
              key={`${e.sourceEventId}-${i}`}
              className="rounded border border-edge/60 bg-surface px-3 py-2 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="code text-xs">{e.sourceEventId}</span>
                <span className="rounded bg-edge px-2 py-0.5 text-xs">
                  {e.eventType}
                </span>
                <span className="text-xs text-muted">
                  authority_ref: {e.authorityRef}
                </span>
                <span className="text-xs text-muted">
                  source_digest: {e.sourceDigest}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted">before</p>
                  <JsonView value={e.before} unknownSentinel={unknownSentinel} />
                </div>
                <div>
                  <p className="text-xs text-muted">after</p>
                  <JsonView value={e.after} unknownSentinel={unknownSentinel} />
                </div>
              </div>
              <div className="mt-2">
                <p className="text-xs text-muted">evidence_refs</p>
                {e.evidenceRefs.length === 0 ? (
                  <p className="code text-xs text-muted">{unknownSentinel}</p>
                ) : (
                  <ul className="code text-xs text-muted">
                    {e.evidenceRefs.map((r, j) => (
                      <li key={j}>
                        <a href={r.startsWith("http") ? r : undefined}>{r}</a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-xs text-muted">
        {withEvidence.length} event(s) carry evidence_refs. SHA/CI/evidence links
        are rendered only when explicitly present in the source fixture.
      </p>
    </div>
  );
}
