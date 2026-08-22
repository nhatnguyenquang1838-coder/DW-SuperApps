import type { SimGate, SimTask, ReplayMode } from "@/lib/simRun";

type Props = {
  task: SimTask;
  gate: SimGate;
  mode: ReplayMode;
  timelineLength: number;
  cursor: number;
};

/**
 * Right-hand detail panel. Pure presentational: shows the selected task's
 * node family, node id, authority boundary, reads/writes artifacts, option,
 * catalog path, and the replay behavior for the active mode.
 */
export default function Inspector({ task, gate, mode, timelineLength, cursor }: Props) {
  const ix = gate.tasks.findIndex((t) => t.task_id === task.task_id);
  const replayNote =
    mode === "REPLAY"
      ? `Clicking this card rewinds cursor to task index ${ix + 1}/${timelineLength}.`
      : "LIVE mode: click selects details only; cursor stays at latest state.";
  return (
    <div className="sr-body" data-testid="sr-inspector">
      <div className="sr-current">
        <div className="sr-current-id">{task.task_id} · {task.node_id}</div>
        <div className="sr-current-name">{task.task_title}</div>
        <div className="sr-current-desc">{task.details}</div>
      </div>
      <Field label="Gate" value={`${gate.id} · ${gate.label}`} />
      <Field label="Node family / Node id" value={`${task.family} / ${task.node_id}`} mono />
      <Field label="Node type / Authority boundary" value={`${task.node_type} / ${task.authority_boundary}`} />
      <Field label="Reads evidence" value={task.reads.join("\n")} list />
      <Field label="Writes artifacts" value={task.writes.join("\n")} mono list />
      <Field label="Primary artifact" value={task.artifact} mono />
      <Field label="Option / decision" value={task.option} />
      <Field label="Catalog / source path" value={task.catalog_path} mono />
      <Field label="Replay behavior" value={replayNote} />
    </div>
  );
}

function Field({ label, value, mono, list }: { label: string; value: string; mono?: boolean; list?: boolean }) {
  return (
    <div className="sr-field">
      <div className="sr-label">{label}</div>
      {list ? (
        <ul className={["sr-value", mono ? "sr-mono" : ""].join(" ")}>
          {value.split("\n").map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      ) : (
        <div className={["sr-value", mono ? "sr-mono" : ""].join(" ")}>{value}</div>
      )}
    </div>
  );
}
