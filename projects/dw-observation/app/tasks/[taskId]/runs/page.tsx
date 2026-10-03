// Server Component — Task → Root runs navigation.
//
// /tasks/[taskId]/runs lists the root runs for a given task, resolved through
// the real TaskRunIndexV2 resolver (resolveFromIndex). No inference from run-id
// or branch patterns: absence of a relation record -> UNKNOWN_UNRESOLVED.
//
// Read-only. Grants no effect capability.

import { notFound } from "next/navigation";
import { getTaskRootRuns, TASK_META } from "@/lib/taskFixtures";
import { listRuns, UNKNOWN } from "@/lib/observatory";

type Json = Record<string, unknown>;

function findTaskMeta(taskId: string) {
  return TASK_META.find((t) => t.taskRef === taskId);
}

export default function TaskRunsPage({ params }: { params: { taskId: string } }) {
  const taskRef = decodeURIComponent(params.taskId);
  const meta = findTaskMeta(taskRef);

  // Fail-closed: unknown task → 404, not a silent fallback.
  if (!meta) notFound();

  const resolution = getTaskRootRuns(taskRef);
  const runsById = new Map(listRuns("mock").map((r) => [r.runId, r]));

  const items = resolution.rootRunIds.map((runId) => {
    const run = runsById.get(runId);
    return {
      id: runId,
      source: run?.sourceSystem ?? UNKNOWN,
      kind: run?.lane ?? UNKNOWN,
      started: run?.startedAt ?? null,
      eventCount: run?.eventCount,
      anomalyCount: run?.anomalyCount,
    };
  });

  return (
    <div
      className="min-h-screen"
      style={{
        background: "#ffffff",
        color: "#37352f",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <div className="mx-auto max-w-5xl px-6 py-10">
        <nav className="mb-6 text-xs" style={{ color: "#9b9a97" }}>
          <a href="/tasks" style={{ color: "#787774" }}>
            Tasks
          </a>{" "}
          / <span style={{ color: "#37352f" }}>{taskRef}</span>
        </nav>

        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: "#37352f" }}
        >
          {taskRef}
        </h1>
        <p className="mb-2 text-sm" style={{ color: "#37352f" }}>
          {meta.title}
        </p>
        <p className="mb-6 text-xs" style={{ color: "#787774" }}>
          domain: {meta.domain} · relation: {resolution.reason} (
          {resolution.status})
        </p>

        {items.length === 0 ? (
          <div
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "#f0b429",
              background: "#fdf6e3",
              color: "#8a6d1a",
            }}
          >
            No root runs resolved for this task — no relation record exists{" "}
            (TaskRunIndexV2 fail-closed, no run-id inference).
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((r) => (
              <a
                key={r.id}
                href={`/runs/${encodeURIComponent(r.id)}`}
                className="notion-run-card block rounded-lg border p-4 transition-colors"
                style={{ color: "inherit" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-sm font-semibold"
                    style={{ color: "#37352f" }}
                  >
                    {r.id}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: "#f1f1ef", color: "#787774" }}
                  >
                    {r.source}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt style={{ color: "#9b9a97" }}>Kind</dt>
                    <dd style={{ color: "#37352f" }}>{r.kind}</dd>
                  </div>
                  <div>
                    <dt style={{ color: "#9b9a97" }}>Started</dt>
                    <dd style={{ color: "#37352f" }}>{r.started ?? "—"}</dd>
                  </div>
                </dl>
                {(r.eventCount !== undefined || r.anomalyCount !== undefined) && (
                  <div className="mt-2 flex gap-2 text-[10px]" style={{ color: "#9b9a97" }}>
                    {r.eventCount !== undefined && <span>{r.eventCount} events</span>}
                    {r.anomalyCount !== undefined && r.anomalyCount > 0 && (
                      <span style={{ color: "#b54708" }}>{r.anomalyCount} anomalies</span>
                    )}
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
        .notion-run-card { border-color: #e9e9e7; background: #ffffff; }
        .notion-run-card:hover { border-color: #37352f; }
        .notion-link-btn { border-color: #d3d1cb; background: #f7f7f5; color: #37352f; }
        .notion-link-btn:hover { background: #efefed; }
      `}</style>
    </div>
  );
}
