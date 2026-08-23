import type { NodeState } from "@/lib/simRun";

/**
 * Animated connector between two adjacent node cards inside a gate.
 * Driven by the two cards' replay states: done -> green, active -> flowing,
 * future -> neutral. Pure presentational; no logic.
 */
export default function Connector({ state }: { state: NodeState }) {
  return <div className={`sr-connector ${state}`} aria-hidden="true" />;
}
