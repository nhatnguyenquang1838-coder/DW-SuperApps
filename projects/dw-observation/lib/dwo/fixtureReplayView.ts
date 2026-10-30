import type { ProjectionEvent } from "@/lib/live";
import { reduceEventPrefix, type ReducerEvent } from "./reducer";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

/** Project only the supplied session prefix; server-built topology remains immutable. */
export function projectFixtureReplayView(
  model: UnifiedRunWorkspaceModel,
  prefix: readonly ProjectionEvent[],
): UnifiedRunWorkspaceModel {
  if (model.projectionStatus === "INCOMPATIBLE") return model;
  const nodeIds = new Set(model.nodes.map((node) => node.id));
  const seen = new Set<string>();
  const positions = new Set<string>();
  const reducerEvents: ReducerEvent[] = prefix.map((event) => {
    const authority = event.authority_state;
    if (typeof event.event_id !== "string" || !event.event_id.trim() ||
        typeof event.run_id !== "string" || !nodeIds.has(event.run_id) ||
        typeof event.ordinal !== "number" || !Number.isSafeInteger(event.ordinal) || event.ordinal < 0 ||
        !(authority === "PENDING" || authority === "GRANTED" || authority === "DENIED" || authority === "EXPIRED" || authority === "REVOKED" || authority === "NOT_REQUIRED" || authority === "UNKNOWN" || authority === "NOT_APPLICABLE")) {
      throw new Error("invalid fixture replay event identity, ordinal or authority");
    }
    const position = `${event.run_id}:${event.ordinal}`;
    if (seen.has(event.event_id) || positions.has(position)) throw new Error("duplicate fixture replay event");
    seen.add(event.event_id); positions.add(position);
    return {
      eventId: event.event_id, runId: event.run_id, ordinal: event.ordinal,
      gate: typeof event.gate === "string" ? event.gate : null,
      gateState: event.gate_state === "CANCELLED" || event.gate_state === "SUPERSEDED" ? null : typeof event.gate_state === "string" ? event.gate_state : null,
      runState: typeof event.run_state === "string" ? event.run_state : null,
      sourceProfile: typeof event.source_profile === "string" ? event.source_profile : undefined,
      syncState: typeof event.sync_state === "string" ? event.sync_state : undefined,
      semanticQualification: typeof event.semantic_qualification === "string" ? event.semantic_qualification : undefined,
      authorityState: authority,
      anomalyCount: typeof event.anomaly_count === "number" ? event.anomaly_count : undefined,
    };
  });
  const reduced = reduceEventPrefix(model.runId, reducerEvents);
  const nodes = model.nodes.map((node) => {
    const facts = reduceEventPrefix(node.id, reducerEvents);
    // Full-tip evidence has no durable-position binding in this fixture pack.
    // Do not expose it as evidence for an arbitrary replay prefix.
    return { ...node, gateId: facts.gate, gateState: facts.gateState,
      sourceStatus: facts.sourceProfile === "UNKNOWN" ? "UNKNOWN" : "ACTIVE",
      fileReads: [], fileWrites: [], artifacts: [], runbook: [],
      taskControllerHistory: [], executorHistory: [], checkpoints: [] };
  });
  const orderedSteps = prefix.map((event, sequence) => ({ nodeId: String(event.run_id), sequence }));
  const terminal = prefix.filter((event) => event.run_id === model.runId).map((event) => event.gate_state)
    .find((state): state is "CANCELLED" | "SUPERSEDED" => state === "CANCELLED" || state === "SUPERSEDED") ?? null;
  return { ...model, status: reduced.runState, gate: reduced.gate, gateState: reduced.gateState,
    sourceTerminalMarker: terminal, sourceProfile: reduced.sourceProfile,
    syncState: reduced.syncState, semanticQualification: reduced.semanticQualification, authorityState: reduced.authorityState,
    anomalyCount: reduced.anomalyCount, nodes, orderedSteps,
    canonicalHistoryAvailable: prefix.length > 0, currentSequence: prefix.length > 0 ? prefix.length - 1 : null,
    projectionStatus: prefix.length > 0 ? reduced.semanticQualification : "UNKNOWN", sourceDigest: null };
}
