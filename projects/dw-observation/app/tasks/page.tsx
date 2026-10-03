// Server Component — Task-first entry point.
//
// /tasks lists all known tasks from the fixture/task index.
// This is the PRIMARY product entry point (DWO v2 Task-first navigation).
//
// Read-only. Grants no effect capability.

import { TASK_META, getTaskRootRuns } from "@/lib/taskFixtures";

export default function TasksPage() {
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
        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: "#37352f" }}
        >
          Tasks
        </h1>
        <p className="mb-6 text-sm" style={{ color: "#787774" }}>
          DW Run Observatory — Task-first navigation (DWO v2)
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {TASK_META.map((t) => {
            const resolution = getTaskRootRuns(t.taskRef);
            const runCount = resolution.rootRunIds.length;
            return (
              <a
                key={t.taskRef}
                href={`/tasks/${encodeURIComponent(t.taskRef)}/runs`}
                className="notion-run-card block rounded-lg border p-4 transition-colors"
                style={{ color: "inherit" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-sm font-semibold"
                    style={{ color: "#37352f" }}
                  >
                    {t.taskRef}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: "#f1f1ef", color: "#787774" }}
                  >
                    {t.domain}
                  </span>
                </div>
                <p className="mt-2 text-sm" style={{ color: "#37352f" }}>
                  {t.title}
                </p>
                <div className="mt-3 flex items-center gap-3 text-xs">
                  <span style={{ color: runCount > 0 ? "#1a7f37" : "#9b9a97" }}>
                    {runCount} run{runCount !== 1 ? "s" : ""}
                  </span>
                  {resolution.status === "UNKNOWN_UNRESOLVED" && (
                    <span
                      className="text-[10px] uppercase"
                      style={{ color: "#b54708" }}
                    >
                      {resolution.reason}
                    </span>
                  )}
                </div>
              </a>
            );
          })}
        </div>

        <div
          className="mt-10 rounded-lg border p-4"
          style={{ borderColor: "#e9e9e7", background: "#ffffff" }}
        >
          <h2 className="text-sm font-semibold" style={{ color: "#37352f" }}>
            Global run explorer
          </h2>
          <p className="mt-1 text-xs" style={{ color: "#787774" }}>
            All runs across tasks (read-only historical projection).
          </p>
          <a
            href="/runs"
            className="notion-link-btn mt-3 inline-block rounded border px-3 py-1.5 text-sm transition-colors"
          >
            Open Run Explorer →
          </a>
        </div>

        <div
          className="mt-6 rounded-lg border px-3 py-1.5 font-mono text-xs"
          style={{ borderColor: "#e9e9e7", color: "#787774" }}
        >
          data-source: task-index · backend: fixture
        </div>
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
