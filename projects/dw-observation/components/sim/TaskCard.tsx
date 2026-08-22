import type { SimTask, TaskState } from "@/lib/simRun";

type Props = {
  task: SimTask;
  state: TaskState;
  selected: boolean;
  onSelect: (taskId: string) => void;
};

const STATE_LABEL: Record<TaskState, string> = {
  done: "DONE",
  active: "ACTIVE",
  future: "TODO",
};

/**
 * One task card in a gate container. Pure presentational: receives its replay
 * state + selection from the parent, emits onSelect. No internal state.
 */
export default function TaskCard({ task, state, selected, onSelect }: Props) {
  return (
    <article
      data-testid="sr-task-card"
      data-task-id={task.task_id}
      data-state={state}
      data-selected={selected ? "true" : "false"}
      className={[
        "sr-task",
        state === "future" ? "sr-task-future" : "",
        state === "done" ? "sr-task-done" : "",
        state === "active" ? "sr-task-active" : "",
        selected ? "sr-task-selected" : "",
      ].join(" ")}
      onClick={() => onSelect(task.task_id)}
    >
      <div className="sr-task-top">
        <span>{task.task_id}</span>
        <span>{STATE_LABEL[state]}</span>
      </div>
      <div className="sr-task-title">{task.task_title}</div>
      <div className="sr-task-note">{task.note}</div>
      <div className="sr-task-desc">{task.description || task.details}</div>
      <div className="sr-meta">
        <span className="sr-mini">{task.family}</span>
        <span className="sr-mini">{task.node_type}</span>
        <span className="sr-mini">{task.authority_boundary}</span>
      </div>
      <div className="sr-artifact">{task.artifact}</div>
    </article>
  );
}
