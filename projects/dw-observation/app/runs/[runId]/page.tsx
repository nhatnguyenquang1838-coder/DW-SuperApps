import { notFound } from "next/navigation";
import { getRun, UNKNOWN } from "@/lib/observatory";
import RootCard from "@/components/RootCard";
import DagView from "@/components/DagView";
import Timeline from "@/components/Timeline";
import EvidenceInspector from "@/components/EvidenceInspector";

export default function RunDetailPage({
  params,
}: {
  params: { runId: string };
}) {
  const run = getRun(params.runId);
  if (!run) {
    notFound();
  }

  return (
    <section className="space-y-6">
      <RootCard run={run} unknownSentinel={UNKNOWN} />

      <DagView gates={run.gates} nodes={run.nodes} />

      <Timeline events={run.events} unknownSentinel={UNKNOWN} />

      <EvidenceInspector
        events={run.events}
        anomalies={run.anomalies}
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
