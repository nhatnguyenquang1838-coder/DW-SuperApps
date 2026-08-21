import { NormalizedEvent } from "@/lib/observatory";

type Props = {
  events: NormalizedEvent[];
  unknownSentinel: string;
};

// Timeline: events rendered in the EXACT order recorded by the run stream
// (the reducer preserves supplied order; it does not reorder). Read-only.
export default function Timeline({ events, unknownSentinel }: Props) {
  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <h2 className="mb-3 text-base font-semibold">Timeline</h2>
      {events.length === 0 ? (
        <p className="text-sm text-muted">{unknownSentinel}</p>
      ) : (
        <ol className="space-y-2">
          {events.map((e, i) => (
            <li
              key={`${e.sourceEventId}-${i}`}
              className="rounded border border-edge/60 bg-surface px-3 py-2 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="code text-xs text-muted">
                  #{i}
                  {e.seq !== null ? ` · seq ${e.seq}` : ""}
                </span>
                <span className="rounded bg-edge px-2 py-0.5 text-xs">
                  {e.eventType}
                </span>
                {e.gate !== unknownSentinel ? (
                  <span className="text-xs text-muted">gate: {e.gate}</span>
                ) : null}
                {e.nodeId !== unknownSentinel ? (
                  <span className="text-xs text-muted">node: {e.nodeId}</span>
                ) : null}
                <span className="code text-xs text-muted">{e.occurredAt}</span>
              </div>
              <p className="mt-1 text-xs text-muted">
                source_event_id: {e.sourceEventId} · actor: {e.actor}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
