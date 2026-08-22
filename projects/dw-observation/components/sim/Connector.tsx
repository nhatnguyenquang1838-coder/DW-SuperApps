import type { TaskState } from "@/lib/simRun";

/**
 * Connector between two adjacent task cards inside a gate. Driven by the two
 * cards' replay states: done -> green, active -> animated flow, future -> idle.
 */
export default function Connector({ fromState, toState }: { fromState: TaskState; toState: TaskState }) {
  const filled = fromState === "done";
  const flowing = fromState === "active" || toState === "active";
  const cls = ["sr-connector", filled ? "sr-connector-done" : "", flowing ? "sr-connector-active" : ""].join(" ");
  return <div data-testid="sr-connector" className={cls} aria-hidden="true" />;
}
