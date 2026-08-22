import { useState } from "react";
import type { SimGate, SimTask, TaskState } from "@/lib/simRun";
import TaskCard from "./TaskCard";
import Connector from "./Connector";

type Props = {
  gate: SimGate;
  isActive: boolean; // the gate containing the cursor's current task
  cursor: number;
  selectedTaskId: string;
  taskState: (taskId: string) => TaskState;
  onSelect: (taskId: string) => void;
};

/**
 * One gate container: header (id/label/summary/count) + horizontal row of
 * task cards joined by connectors. Collapsible via the header click.
 */
export default function GateContainer({
  gate,
  isActive,
  cursor,
  selectedTaskId,
  taskState,
  onSelect,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <section
      data-testid="sr-gate"
      data-gate-id={gate.id}
      data-active={isActive ? "true" : "false"}
      className={["sr-gate", isActive ? "sr-gate-active" : "", collapsed ? "sr-gate-collapsed" : ""].join(" ")}
    >
      <div className="sr-gate-head" onClick={() => setCollapsed((c) => !c)}>
        <div>
          <div className="sr-gate-id">{gate.id}</div>
          <div className="sr-gate-label">{gate.label}</div>
        </div>
        <div className="sr-gate-summary">{gate.summary}</div>
        <div className="sr-gate-meta">
          <span className="sr-count">{gate.tasks.length} TASKS</span>
          <span className="sr-chev">▼</span>
        </div>
      </div>
      {!collapsed && (
        <div className="sr-gate-body">
          <div className="sr-cards" data-testid="sr-gate-cards">
            {gate.tasks.map((task: SimTask, i: number) => {
              const state = taskState(task.task_id);
              const next = gate.tasks[i + 1];
              return (
                <div className="sr-card-wrap" key={task.task_id}>
                  <TaskCard
                    task={task}
                    state={state}
                    selected={selectedTaskId === task.task_id}
                    onSelect={onSelect}
                  />
                  {next && <Connector fromState={state} toState={taskState(next.task_id)} />}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
