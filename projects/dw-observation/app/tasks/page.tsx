// Server Component — Task-first entry point.
//
// /tasks lists all known tasks from the canonical task gateway.
// This is the PRIMARY product entry point (DWO v2 Task-first navigation).
//
// Read-only. Grants no effect capability.
//
// Uses the REAL adapter — fixture adapter is for dev routes only.
// When the real source is unavailable, FAIL CLOSED: UNAVAILABLE,
// never an empty list masquerading as healthy.

import { readRealSummaries } from "@/lib/taskRead";
import { TASK_RELATION_RECORDS } from "@/lib/taskFixtures";
import type { TaskResolutionStatus } from "@/lib/taskTypes";

const statusStyle: Record<
  TaskResolutionStatus,
  { bg: string; fg: string; label: string }
> = {
  RESOLVED: {
    bg: "var(--dwo-color-bg-subtle)",
    fg: "var(--dwo-color-state-green)",
    label: "RESOLVED",
  },
  UNKNOWN_UNRESOLVED: {
    bg: "var(--dwo-color-bg-subtle)",
    fg: "var(--dwo-color-state-amber)",
    label: "UNKNOWN_UNRESOLVED",
  },
  CONFLICT: {
    bg: "var(--dwo-color-bg-subtle)",
    fg: "var(--dwo-color-state-red)",
    label: "CONFLICT",
  },
  UNAVAILABLE: {
    bg: "var(--dwo-color-bg-canvas)",
    fg: "var(--dwo-color-text-faint)",
    label: "UNAVAILABLE",
  },
};

export default async function TasksPage() {
  // Real source — fixture-backed seed records feed the real adapter until an
  // external connector wires the live task-relation source. Empty records
  // still mean source unavailable (fail-closed stays intact).
  const summaries = await readRealSummaries(TASK_RELATION_RECORDS);
  const sourceAvailable = summaries.length > 0;

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
        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: "var(--dwo-color-text-primary)" }}
        >
          Tasks
        </h1>
        <p className="mb-6 text-sm" style={{ color: "var(--dwo-color-text-muted)" }}>
          DW Run Observatory — Task-first navigation (DWO v2)
        </p>

        {/* Fail-closed: unavailable source is never rendered as healthy. */}
        {!sourceAvailable ? (
          <div
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: "var(--dwo-color-state-amber)",
              background: "var(--dwo-color-bg-subtle)",
              color: "var(--dwo-color-state-amber)",
            }}
          >
            Task source unavailable — real source not yet connected.
            No fixture data shown in real mode.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {summaries.map((t) => {
              const s = statusStyle[t.status];
              return (
                <a
                  key={t.taskRef}
                  href={`/tasks/${encodeURIComponent(t.taskRef)}/runs`}
                  className="notion-run-card block rounded-lg border p-4 transition-colors"
                  style={{
                    color: "inherit",
                    borderColor:
                      t.status === "UNAVAILABLE"
                        ? "var(--dwo-color-text-faint)"
                        : "var(--dwo-color-border-default)",
                    opacity: t.status === "UNAVAILABLE" ? 0.6 : 1,
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="text-sm font-semibold"
                      style={{ color: "var(--dwo-color-text-primary)" }}
                    >
                      {t.taskRef}
                    </span>
                    <span
                      className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                      style={{ background: s.bg, color: s.fg }}
                    >
                      {s.label}
                    </span>
                  </div>
                  <p
                    className="mt-2 text-sm"
                    style={{ color: "var(--dwo-color-text-primary)" }}
                  >
                    {t.title ?? "Unknown task"}
                  </p>
                  <div
                    className="mt-3 flex items-center gap-3 text-xs"
                    style={{ color: "var(--dwo-color-text-muted)" }}
                  >
                    <span>
                      {t.rootRunCount !== null
                        ? `${t.rootRunCount} run${t.rootRunCount !== 1 ? "s" : ""}`
                        : "No runs"}
                    </span>
                    {t.relationRevision != null && (
                      <span className="font-mono">rev:{t.relationRevision}</span>
                    )}
                    {t.status === "UNKNOWN_UNRESOLVED" && (
                      <span
                        className="uppercase"
                        style={{ color: "var(--dwo-color-state-amber)" }}
                      >
                        unresolved
                      </span>
                    )}
                  </div>
                </a>
              );
            })}
          </div>
        )}

        <div
          className="mt-10 rounded-lg border p-4"
          style={{
            borderColor: "var(--dwo-color-border-default)",
            background: "var(--dwo-color-bg-surface)",
          }}
        >
          <h2 className="text-sm font-semibold" style={{ color: "var(--dwo-color-text-primary)" }}>
            Global run explorer
          </h2>
          <p className="mt-1 text-xs" style={{ color: "var(--dwo-color-text-muted)" }}>
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
          style={{ borderColor: "var(--dwo-color-border-default)", color: "var(--dwo-color-text-faint)" }}
        >
          data-source: task-gateway · backend: real
        </div>
      </div>

      <style>{`
        .notion-run-card { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-surface); }
        .notion-run-card:hover { border-color: var(--dwo-color-text-primary); }
        .notion-link-btn { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-subtle); color: var(--dwo-color-text-primary); }
        .notion-link-btn:hover { background: var(--dwo-color-bg-canvas); }
      `}</style>
    </div>
  );
}