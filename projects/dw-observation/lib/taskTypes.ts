export type TaskResolutionStatus =
  | "RESOLVED"
  | "UNKNOWN_UNRESOLVED"
  | "CONFLICT"
  | "UNAVAILABLE";

export interface TaskSummary {
  taskRef: string;
  title: string | null;
  domain: string | null;
  rootRunCount: number | null;
  latestRunId: string | null;
  latestState: string | null;
  relationRevision: number | null;
  status: TaskResolutionStatus;
  /** Root run ids from the resolved relation — used by /tasks/[taskId]/runs hydration. */
  rootRunIds: readonly string[];
}