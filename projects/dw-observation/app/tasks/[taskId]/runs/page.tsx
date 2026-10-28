// Server Component — Task → Root runs navigation.
//
// /tasks/[taskId]/runs lists the root runs for a given task, resolved through
// the canonical task gateway (resolveTask). Uses the REAL adapter — the
// fixture adapter is for dev routes only.
//
// Read-only. Grants no effect capability.

import Link from "next/link";
import { resolveTask } from "@/lib/taskRead";
import { readServerRunList } from "@/lib/serverRunRead";

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

export default async function TaskRunsPage({ params }: { params: { taskId: string } }) {
  const taskRef = decodeURIComponent(params.taskId);

  // Resolve task only through the canonical real relation source. This source
  // is currently not configured, so the resolver returns UNAVAILABLE rather
  // than consuming development fixtures or guessing membership.
  const task = await resolveTask(taskRef, "real", []);

  // Hydrate matching runs from the same real server read boundary. If the
  // canonical relation source is unavailable, do not query fixture-backed views.
  const runList = task.status === "RESOLVED" ? await readServerRunList() : null;
  const runsById = new Map(
    (runList?.runs ?? [])
      .map((run) => [String(run.run_id ?? ""), run] as const)
      .filter(([runId]) => runId.length > 0),
  );

  const items: TaskRunSummary[] = task.rootRunIds.map((runId) => {
    const run = runsById.get(runId);
    return {
      runId,
      status: "UNKNOWN",
      sourceSystem: typeof run?.source_system === "string" ? run.source_system : null,
      lane: null,
      startedAt: typeof run?.started_at === "string" ? run.started_at : null,
      lifecycleProgress: null,
      anomalyCount: null,
      relationRevision: task.relationRevision,
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
          {task.title}
        </p>
        <p className="mb-6 text-xs" style={{ color: "var(--dwo-color-text-muted)" }}>
          domain: {task.domain} · relation: {task.status}
          {task.relationRevision != null && ` · relationRevision: ${task.relationRevision}`}
        </p>

        {task.status !== "RESOLVED" ? (
          <div
            role="status"
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor:
                task.status === "CONFLICT"
                  ? "var(--dwo-color-state-red)"
                  : "var(--dwo-color-state-amber)",
              background: "var(--dwo-color-bg-subtle)",
              color:
                task.status === "CONFLICT"
                  ? "var(--dwo-color-state-red)"
                  : "var(--dwo-color-state-amber)",
            }}
          >
            {task.status === "UNAVAILABLE"
              ? "Task relation unavailable — canonical source is not connected."
              : task.status === "CONFLICT"
                ? "Task relation conflict — no run links were selected."
                : "Task relation unresolved — no run ids are inferred."}
          </div>
        ) : runList?.degraded ? (
          <div
            role="status"
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "var(--dwo-color-state-amber)",
              background: "var(--dwo-color-bg-subtle)",
              color: "var(--dwo-color-state-amber)",
            }}
          >
            Run source unavailable — no fixture fallback is used.
          </div>
        ) : items.length === 0 ? (
          <div
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "var(--dwo-color-state-amber)",
              background: "var(--dwo-color-bg-subtle)",
              color: "var(--dwo-color-state-amber)",
            }}
          >
            No root runs resolved for this task — no relation record exists
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