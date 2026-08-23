import { RunView, UNKNOWN } from "@/lib/observatory";

type SupabaseReadiness = {
  project: string;
  status: string;
  readiness: string;
  publicTables: number;
  migrations: number;
  remoteApplyPerformed: boolean;
};

type Props = {
  run: RunView;
  unknownSentinel: string;
  supabaseReadiness?: SupabaseReadiness;
};

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="code">{value && value !== UNKNOWN ? value : UNKNOWN}</dd>
    </div>
  );
}

// G3 correction #2: complete RootCard. Every labeled field is source-backed
// when present in the fixture; absent fields render the explicit UNKNOWN
// sentinel (never inferred).
export default function RootCard({ run, unknownSentinel, supabaseReadiness }: Props) {
  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Run RootCard</h1>
        <span className="rounded bg-edge px-2 py-0.5 text-xs text-muted">
          read-only
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
        <Field label="Run" value={run.runId} />
        <Field label="Source system" value={run.sourceSystem} />
        <Field label="Started" value={run.startedAt} />
        <Field label="Last event" value={run.lastEventAt} />
        <Field label="Lane" value={run.lane} />
        <Field label="Task" value={run.task} />
        <Field label="Controller" value={run.controller} />
        <Field label="Executor" value={run.executor} />
        <Field label="Gate" value={Object.keys(run.gates)[0] ?? null} />
        <Field label="Branch" value={run.branch} />
        <Field label="PR" value={run.pr} />
        <Field label="Exact HEAD" value={run.exactHead} />
        <Field label="Exact-bound CI" value={run.ci} />
        <Field label="Risk" value={run.risk} />
        <Field label="Blocker" value={run.blocker} />
        <Field label="Now" value={run.now} />
        <Field label="Next" value={run.next} />
        <div>
          <dt className="text-muted">Events / Anomalies</dt>
          <dd className="code">
            {run.eventCount} / {run.anomalyCount}
          </dd>
        </div>
        {supabaseReadiness && (
          <div className="col-span-2 sm:col-span-4">
            <dt className="text-muted">Supabase readiness</dt>
            <dd className="code">
              {supabaseReadiness.project} · {supabaseReadiness.status} ·{" "}
              {supabaseReadiness.readiness} · tables={supabaseReadiness.publicTables}{" "}
              migrations={supabaseReadiness.migrations}{" "}
              remoteApply={String(supabaseReadiness.remoteApplyPerformed)}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}
