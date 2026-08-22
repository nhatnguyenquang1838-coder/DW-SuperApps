/**
 * M5 (G0-G6 simulated run) — data + pure replay engine.
 *
 * Clean separation:
 *   - types describe the visualization model (gate container -> task cards).
 *   - pure functions derive timeline + per-task replay state from a cursor.
 *   - NO React, NO DOM here. The UI layer (components/SimRunView.tsx) consumes
 *     these. This makes the replay logic unit-testable without jsdom.
 *
 * Data source: fixtures/simRunG0G6.ts (typed port of the prototype HTML).
 */

export type TaskState = "done" | "active" | "future";

export interface SimTask {
  task_id: string; // e.g. "G0-T01"
  task_title: string;
  node_id: string; // e.g. "intake_context.source-resolution"
  family: string; // node family
  node_type: string; // workflow|gate|tool|schema|connector|artifact|projection
  authority_boundary: string; // read_only|g2_required|g3_required|g5_required|gate_required
  catalog_path: string;
  title: string;
  description: string;
  details: string;
  note: string;
  reads: string[];
  writes: string[];
  artifact: string;
  option: string;
}

export interface SimGate {
  id: string; // e.g. "G0_CONTEXT"
  label: string;
  summary: string;
  tasks: SimTask[];
}

export interface SimRun {
  run_id: string;
  title: string;
  source_note: string;
  gates: SimGate[];
}

export interface TimelineStep {
  gate_id: string;
  gate_label: string;
  task_id: string;
  taskIndexWithinGate: number;
}

export type ReplayMode = "REPLAY" | "LIVE";

/** Flatten gates -> ordered timeline, preserving gate order and intra-gate order. */
export function buildTimeline(run: SimRun): TimelineStep[] {
  const steps: TimelineStep[] = [];
  for (const gate of run.gates) {
    gate.tasks.forEach((task, taskIndexWithinGate) => {
      steps.push({
        gate_id: gate.id,
        gate_label: gate.label,
        task_id: task.task_id,
        taskIndexWithinGate,
      });
    });
  }
  return steps;
}

export function taskIndexById(run: SimRun, taskId: string): number {
  return buildTimeline(run).findIndex((s) => s.task_id === taskId);
}

export function findTask(run: SimRun, taskId: string): { gate: SimGate; task: SimTask } | null {
  for (const gate of run.gates) {
    const task = gate.tasks.find((t) => t.task_id === taskId);
    if (task) return { gate, task };
  }
  return null;
}

/** Replay state of a task relative to the cursor (index into the timeline). */
export function taskStateAt(run: SimRun, taskId: string, cursor: number): TaskState {
  const i = taskIndexById(run, taskId);
  if (i < 0) return "future";
  if (i < cursor) return "done";
  if (i === cursor) return "active";
  return "future";
}

/**
 * Selector key used by the UI: a task id, or a gate id (active gate highlight).
 * Returns the task id that should be selected given the current cursor.
 */
export function selectedTaskAt(run: SimRun, cursor: number, requested?: string): string {
  const timeline = buildTimeline(run);
  if (requested && findTask(run, requested)) return requested;
  if (cursor < 0 || cursor >= timeline.length) return timeline[0]?.task_id ?? "";
  return timeline[cursor].task_id;
}

export function activeGateIdAt(run: SimRun, cursor: number): string | null {
  const timeline = buildTimeline(run);
  if (cursor < 0 || cursor >= timeline.length) return timeline[timeline.length - 1]?.gate_id ?? null;
  return timeline[cursor].gate_id;
}

/** Clamp a cursor to a valid timeline position. */
export function clampCursor(cursor: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(length - 1, cursor));
}
