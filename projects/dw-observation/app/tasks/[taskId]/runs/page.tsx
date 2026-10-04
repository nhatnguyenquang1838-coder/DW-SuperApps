// Server Component — Task → Root runs navigation.
//
// /tasks/[taskId]/runs lists the root runs for a given task, resolved through
// the real TaskRunIndexV2 resolver (resolveFromIndex). No inference from run-id
// or branch patterns: absence of a relation record -> UNKNOWN_UNRESOLVED.
//
// Read-only. Grants no effect capability.

import { notFound } from "next/navigation";
import Link from "next/link";
import { resolveFromIndex, buildTaskRunIndexV2 } from "@/lib/dwo/taskRunIndex";
import { TASK_META, TASK_RELATION_RECORDS } from "@/lib/taskFixtures";
import { listRuns } from "@/lib/observatory";

type TaskRunSummary = {
  runId: string;
  status: string;
  sourceSystem: string | null;
  lane: string | null;
  startedAt: string | null;
  lifecycleProgress: { completed: number; total: number } | null;
  anomalyCount: number | null;
  relationRevision: number | null;
};

function findTaskMeta(taskId: string) {
  return TASK_META.find((t) => t.taskRef === taskId);
}

export default function TaskRunsPage({ params }: { params: { taskId: string } }) {
  const taskRef = decodeURIComponent(params.taskId);
  const meta = findTaskMeta(taskRef);

  // Fail-closed: unknown task → 404, not a silent fallback.
  if (!meta) notFound();

  // Resolve relation through source-backed gateway (T02 pattern).
  const index = buildTaskRunIndexV2(TASK_RELATION_RECORDS);
  const decision = resolveFromIndex(index, taskRef);

  // Hydrate run metadata from the same source (real fixtures, not mock).
  const runsById = new Map(listRuns("real").map((r) => [r.runId, r]));

  const items: TaskRunSummary[] = decision.rootRunIds.map((runId) => {
    const run = runsById.get(runId);
    return {
      runId,
      status: run?.next ?? "—",
      sourceSystem: run?.sourceSystem && run.sourceSystem !== "—" ? run.sourceSystem : null,
      lane: run?.lane && run.lane !== "—" ? run.lane : null,
      startedAt: run?.startedAt ?? null,
      lifecycleProgress: null,
      anomalyCount: run?.anomalyCount ?? null,
      relationRevision: decision.relationRevisionId
        ? Number.parseInt(decision.relationRevisionId.replace("rel-", ""), 10)
        : null,
    };
  });

  return (
    <div
      className="min-h-screen"
      style={{
        background: "var(--dwo-color-bg-canvas)",
        color: "var(--dwo-color-text-primary)",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <div className="mx-auto max-w-5xl px-6 py-10">
        <nav className="mb-6 text-xs" style={{ color: "var(--dwo-color-text-faint)" }}>
          <Link href="/tasks" style={{ color: "var(--dwo-color-text-muted)" }}>
            Tasks
          </Link>{" "}
          / <span style={{ color: "var(--dwo-color-text-primary)" }}>{taskRef}</span>
        </nav>

        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: "var(--dwo-color-text-primary)" }}
        >
          {taskRef}
        </h1>
        <p className="mb-2 text-sm" style={{ color: "var(--dwo-color-text-primary)" }}>
          {meta.title}
        </p>
        <p className="mb-6 text-xs" style={{ color: "var(--dwo-color-text-muted)" }}>
          domain: {meta.domain} · relation: {decision.reason} (
          {decision.status})
          {decision.relationRevisionId
            ? ` · relationRevision: ${decision.relationRevisionId}`
            : ""}
        </p>

        {items.length === 0 ? (
          <div
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "var(--dwo-color-state-amber)",
              background: "var(--dwo-color-bg-subtle)",
              color: "var(--dwo-color-state-amber)",
            }}
          >
            No root runs resolved for this task — no relation record exists{" "}
            (TaskRunIndexV2 fail-closed, no run-id inference).
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((r) => (
              <a
                key={r.runId}
                href={`/runs/${encodeURIComponent(r.runId)}`}
                className="notion-run-card block rounded-lg border p-4 transition-colors"
                style={{ color: "inherit" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-sm font-semibold"
                    style={{ color: "var(--dwo-color-text-primary)" }}
                  >
                    {r.runId}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: "var(--dwo-color-bg-subtle)", color: "var(--dwo-color-text-muted)" }}
                  >
                    {r.sourceSystem ?? "—"}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt style={{ color: "var(--dwo-color-text-faint)" }}>Status</dt>
                    <dd style={{ color: "var(--dwo-color-text-primary)" }}>{r.status}</dd>
                  </div>
                  <div>
                    <dt style={{ color: "var(--dwo-color-text-faint)" }}>Lane</dt>
                    <dd style={{ color: "var(--dwo-color-text-primary)" }}>{r.lane ?? "—"}</dd>
                  </div>
                  <div>
                    <dt style={{ color: "var(--dwo-color-text-faint)" }}>Started</dt>
                    <dd style={{ color: "var(--dwo-color-text-primary)" }}>
                      {r.startedAt ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt style={{ color: "var(--dwo-color-text-faint)" }}>Anomalies</dt>
                    <dd style={{ color: "var(--dwo-color-text-primary)" }}>
                      {r.anomalyCount !== null && r.anomalyCount !== undefined
                        ? r.anomalyCount
                        : "—"}
                    </dd>
                  </div>
                </dl>
                {r.relationRevision !== null && (
                  <div className="mt-2 text-[10px]" style={{ color: "var(--dwo-color-text-faint)" }}>
                    relationRevision: {r.relationRevision}
                  </div>
                )}
              </a>
            ))}
          </div>
        )}

        <a
          href="/tasks"
          className="notion-link-btn mt-8 inline-block rounded border px-3 py-1.5 text-sm transition-colors"
        >
          ← Back to tasks
        </a>
      </div>

      <style>{`
        .notion-run-card { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-surface); }
        .notion-run-card:hover { border-color: var(--dwo-color-accent-blue); }
        .notion-link-btn { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-subtle); color: var(--dwo-color-text-primary); }
        .notion-link-btn:hover { background: var(--dwo-color-bg-surface); }
      `}</style>
    </div>
  );
}