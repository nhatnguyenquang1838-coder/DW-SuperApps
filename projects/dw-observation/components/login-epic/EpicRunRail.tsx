import type { LoginEpicRun } from "@/lib/loginEpicRuntimeGraph";

/**
 * EpicRunRail — the top-level 10-run epic graph. One card per run, run arrows
 * R00 -> R09. Clicking a run resets cursor to 0 and loads its run-level graph.
 */
export default function EpicRunRail({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: LoginEpicRun[];
  selectedRunId: string;
  onSelectRun: (runId: string) => void;
}) {
  return (
    <section className="leg-epic" data-testid="login-epic-run-graph">
      <h2>1 · Epic Run Graph (click a run · R00 → R09)</h2>
      <div className="leg-epic-cards">
        {runs.map((r, i) => (
          <div key={r.id} className="leg-epic-pair">
            <button
              className={`leg-run-card${selectedRunId === r.id ? " active" : ""}`}
              data-testid="login-epic-run-card"
              data-run-id={r.id}
              onClick={() => onSelectRun(r.id)}
            >
              <div className="leg-run-idx">R{String(r.index).padStart(2, "0")}</div>
              <div className="leg-run-id">{r.id}</div>
              <div className="leg-run-kind">{r.run_kind}</div>
              <div className="leg-run-summary">{r.summary}</div>
            </button>
            {i < runs.length - 1 && (
              <span className="leg-run-arrow" data-testid="login-epic-run-arrow" aria-hidden>
                →
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
