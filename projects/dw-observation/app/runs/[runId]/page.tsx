import { notFound } from "next/navigation";
import { getRun, UNKNOWN } from "@/lib/observatory";
import RootCard from "@/components/RootCard";
import DagView from "@/components/DagView";
import Timeline from "@/components/Timeline";
import EvidenceInspector from "@/components/EvidenceInspector";

function asArray(v: unknown): Array<Record<string, unknown>> {
  return Array.isArray(v) ? (v as Array<Record<string, unknown>>) : [];
}

function asRecord(v: unknown): Record<string, Record<string, unknown>> {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, Record<string, unknown>>;
  }
  return {};
}

export default function RunDetailPage({
  params,
}: {
  params: { runId: string };
}) {
  const bundle = getRun(params.runId);
  if (!bundle) {
    notFound();
  }
  const proj = bundle!.projection;
  const events = asArray(proj.events);
  const anomalies = asArray(proj.anomalies);
  const gates = asRecord(proj.gates);
  const nodes = asRecord(proj.nodes);

  return (
    <section className="space-y-6">
      <RootCard
        runId={(proj.run_id as string) ?? params.runId}
        startedAt={(proj.started_at as string | null) ?? null}
        lastEventAt={(proj.last_event_at as string | null) ?? null}
        eventCount={events.length}
        anomalyCount={anomalies.length}
      />

      <DagView gates={gates} nodes={nodes} />

      <Timeline events={events} />

      <EvidenceInspector
        events={events}
        anomalies={anomalies}
        unknownSentinel={UNKNOWN}
      />

      <p className="text-xs text-muted">
        This is a read-only historical projection. No authority, gate, or live
        state is inferred beyond what the source fixture records. Missing values
        are shown explicitly as &ldquo;{UNKNOWN}&rdquo;.
      </p>
    </section>
  );
}
