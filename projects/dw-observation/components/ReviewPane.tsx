"use client";

// M4 — review intelligence surface.
//
// Renders derived metrics (duration, wait, retries, recoveries, handoffs) from
// the SAME immutable projection events, and shows the exact source refs each
// aggregate was computed from so a reviewer can trace any number back.
//
// Read-only: this pane derives, it never asserts governance authority. Values
// that the source does not record are shown explicitly as UNKNOWN with an
// incompleteness marker — never as zero.

import { useMemo } from "react";
import type { ProjectionEvent } from "@/lib/live";
import { UNKNOWN } from "@/lib/replay";
import {
  type Metric,
  type TraceRef,
  reviewRun,
} from "@/lib/reviewIntelligence";

export interface ReviewPaneProps {
  runId: string;
  events: ProjectionEvent[];
  storeDegraded?: boolean;
}

function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return UNKNOWN;
  const totalSeconds = Math.round(value / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function TraceList({ trace, testId }: { trace: TraceRef[]; testId: string }) {
  if (trace.length === 0) {
    return <p data-testid={`${testId}-trace-empty`}>{UNKNOWN}</p>;
  }
  return (
    <ul data-testid={`${testId}-trace`}>
      {trace.map((t, i) => (
        <li key={`${t.sourceSystem}-${t.sourceEventId}-${i}`} data-testid={`${testId}-trace-ref`}>
          {t.sourceSystem}/{t.sourceEventId} · seq{" "}
          {t.sequence === null ? UNKNOWN : t.sequence} · {t.eventType}
          {t.evidenceRefs.length > 0 ? ` · ${t.evidenceRefs.join(", ")}` : ""}
          {t.authorityRef ? ` · authority ${t.authorityRef}` : ""}
        </li>
      ))}
    </ul>
  );
}

function MetricRow<T>({
  metric,
  label,
  testId,
  render,
}: {
  metric: Metric<T>;
  label: string;
  testId: string;
  render: (value: T) => string;
}) {
  return (
    <div data-testid={testId}>
      <h4>{label}</h4>
      <p data-testid={`${testId}-value`}>
        {metric.value === null ? UNKNOWN : render(metric.value)}
      </p>
      <p data-testid={`${testId}-confidence`}>{metric.confidence}</p>
      {metric.incomplete.length > 0 && (
        <p data-testid={`${testId}-incomplete`}>{metric.incomplete.join(", ")}</p>
      )}
      <TraceList trace={metric.trace} testId={testId} />
    </div>
  );
}

export default function ReviewPane({ runId, events, storeDegraded = false }: ReviewPaneProps) {
  const report = useMemo(() => reviewRun(runId, events), [runId, events]);

  if (events.length === 0) {
    return (
      <section aria-label="Review intelligence" data-testid="review-pane">
        <h2>Review intelligence</h2>
        <p data-testid="review-empty">
          {storeDegraded
            ? "PROJECTION_UNAVAILABLE — durable history unreadable; no metrics derived."
            : "No projection events; no metrics derived."}
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Review intelligence" data-testid="review-pane">
      <header>
        <h2>Review intelligence</h2>
        <span data-testid="review-reducer-version">{report.reducerVersion}</span>
        <span data-testid="review-event-count">{report.eventCount} events</span>
        <span data-testid="review-complete">
          {report.historyComplete ? "HISTORY_COMPLETE" : "HISTORY_INCOMPLETE"}
        </span>
        {report.anomalyCount > 0 && (
          <span data-testid="review-anomaly-count">{report.anomalyCount} anomalies</span>
        )}
      </header>

      {report.incompleteMarkers.length > 0 && (
        <p data-testid="review-markers">{report.incompleteMarkers.join(", ")}</p>
      )}

      <MetricRow
        metric={report.duration}
        label="Duration"
        testId="metric-duration"
        render={(v) =>
          `${ms(v.totalMs)}${v.terminated ? "" : " (elapsed, not terminated)"}`
        }
      />

      <MetricRow
        metric={report.longestWait}
        label="Longest wait"
        testId="metric-wait"
        render={(v) => `${ms(v.ms)} (${v.fromEventId} → ${v.toEventId})`}
      />

      <MetricRow
        metric={report.retries}
        label="Retries"
        testId="metric-retries"
        render={(v) =>
          v.length === 0
            ? "none recorded"
            : v.map((s) => `${s.key}: ${s.attempts} attempts`).join("; ")
        }
      />

      <MetricRow
        metric={report.recoveries}
        label="Recoveries"
        testId="metric-recoveries"
        render={(v) =>
          v
            .map((s) =>
              s.recovered
                ? `${s.target}: recovered in ${ms(s.ms)}`
                : `${s.target}: NOT RECOVERED`
            )
            .join("; ")
        }
      />

      <MetricRow
        metric={report.handoffs}
        label="Handoffs"
        testId="metric-handoffs"
        render={(v) =>
          v.length === 0
            ? "none recorded"
            : v.map((h) => `${h.fromActor} → ${h.toActor} (${ms(h.ms)})`).join("; ")
        }
      />

      <p data-testid="review-note">
        Metrics are derived read-only from recorded projection events. This pane
        creates no authority and mutates nothing; unknown values are shown as
        &ldquo;{UNKNOWN}&rdquo; rather than assumed.
      </p>
    </section>
  );
}
