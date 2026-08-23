/**
 * M5 (G0-G6 simulated run) — CORRECTED node-architect model.
 *
 * Mental model (per corrected architect):
 *   Gate → Runtime Nodes. Each NODE is the runtime unit; its artifacts,
 *   runbook, TaskController history, Executor history and checkpoints are
 *   children/details of the node (not "Gate → Task Card").
 *
 * Clean separation:
 *   - types describe the visualization model (gate container -> node card).
 *   - pure functions derive the replay timeline + per-cursor state from the
 *     data, with ZERO React/DOM and ZERO randomness (fully unit-testable,
 *     deterministic — verification is code-driven, not LLM visual judgment).
 */

export type ReplayMode = "REPLAY" | "LIVE";

/** A history event attached to a node or a gate. */
export interface HistoryEvent {
  event_id: string;
  type: string;
  actor: string;
  outcome: string;
  evidence?: string[];
}

/** A runtime checkpoint attached to a node. */
export interface Checkpoint {
  checkpoint_id: string;
  revision: number;
  current_node_id: string;
  next_node_id: string;
  lease_owner: string;
  fencing_token: string;
  status: string;
}

/** A runtime NODE card living inside a gate. */
export interface SimNode {
  node_id: string;
  title: string;
  description: string;
  node_type: string;
  family: string;
  authority_boundary: string;
  catalog_path?: string;
  source_status?: string;
  maturity?: string;
  implementation_refs?: string[];
  declared_gates?: string[];
  canonical?: string;
  gate_id: string;
  gate_label?: string;
  sequence: number;
  node_label?: string;
  artifacts: string[];
  reads: string[];
  runbook: string[];
  taskcontroller_history: HistoryEvent[];
  executor_history: HistoryEvent[];
  checkpoints: Checkpoint[];
  options?: string[];
}

/** A GATE container holding node cards. */
export interface SimGate {
  id: string;
  label: string;
  summary: string;
  nodes: SimNode[];
  gate_artifacts: string[];
  taskcontroller_history: HistoryEvent[];
  executor_history: HistoryEvent[];
}

/** Top-level run. */
export interface SimRun {
  run_id: string;
  task_id: string;
  repository: string;
  base_branch: string;
  base_sha: string;
  graph_revision?: Record<string, unknown>;
  status: string;
  source_basis?: Record<string, unknown>;
  gates: SimGate[];
}

/** Replay state of a node at a given cursor. */
export type NodeState = "done" | "active" | "future";

/** One step in the deterministic replay timeline. */
export interface TimelineStep {
  gate_id: string;
  node_id: string;
  sequence: number;
}

const byId = <T extends { id: string }>(xs: T[], id: string): T | undefined =>
  xs.find((x) => x.id === id);

export function getGate(run: SimRun, gateId: string): SimGate | undefined {
  return byId(run.gates, gateId);
}

export function getNode(
  run: SimRun,
  gateId: string,
  nodeId: string,
): SimNode | undefined {
  return getGate(run, gateId)?.nodes.find((n) => n.node_id === nodeId);
}

/**
 * Build the replay timeline by flattening nodes in sequence order.
 * Single source of truth: node.sequence (identical to the prototype TIMELINE).
 */
export function buildTimeline(run: SimRun): TimelineStep[] {
  return run.gates
    .flatMap((g) => g.nodes)
    .slice()
    .sort((a, b) => a.sequence - b.sequence)
    .map((n) => ({ gate_id: n.gate_id, node_id: n.node_id, sequence: n.sequence }));
}

export function timelineLength(run: SimRun): number {
  return buildTimeline(run).length;
}

/** Index of a node in the timeline, or -1. */
export function indexOfNode(
  run: SimRun,
  gateId: string,
  nodeId: string,
): number {
  return buildTimeline(run).findIndex(
    (s) => s.gate_id === gateId && s.node_id === nodeId,
  );
}

/** Replay state of a node at a cursor (0-based). */
export function nodeStateAt(
  run: SimRun,
  gateId: string,
  nodeId: string,
  cursor: number,
): NodeState {
  const ix = indexOfNode(run, gateId, nodeId);
  if (ix < 0) return "future";
  if (ix < cursor) return "done";
  if (ix === cursor) return "active";
  return "future";
}

/** The gate id that owns the node active at the cursor (or undefined). */
export function activeGateIdAt(run: SimRun, cursor: number): string | undefined {
  return buildTimeline(run)[cursor]?.gate_id;
}

/** Clamp a cursor into [0, len-1]. */
export function clampCursor(run: SimRun, cursor: number): number {
  const len = timelineLength(run);
  if (len === 0) return 0;
  return Math.max(0, Math.min(len - 1, cursor));
}

/**
 * Selection can be a node (default) or a gate summary.
 */
export type Selection =
  | { kind: "node"; gateId: string; nodeId: string }
  | { kind: "gate"; gateId: string };

/** Resolve the node that should be selected at a cursor (first node of step). */
export function selectedNodeAt(
  run: SimRun,
  cursor: number,
): Selection {
  const step = buildTimeline(run)[clampCursor(run, cursor)];
  if (!step) return { kind: "gate", gateId: run.gates[0]?.id ?? "" };
  return { kind: "node", gateId: step.gate_id, nodeId: step.node_id };
}

/** Determine if a gate is the active one at a cursor. */
export function isGateActiveAt(
  run: SimRun,
  gateId: string,
  cursor: number,
): boolean {
  return activeGateIdAt(run, cursor) === gateId;
}
