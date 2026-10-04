import type { UnifiedRunWorkspaceModel, UnifiedRuntimeNode, RuntimeNodeState, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";

// ---------------------------------------------------------------------------
// Shared fixture data for DWO Storybook stories
// All data is local — zero network dependency.
// ---------------------------------------------------------------------------

export const makeNode = (overrides: Partial<UnifiedRuntimeNode>): UnifiedRuntimeNode => ({
  id: overrides.id ?? "node-1",
  gateId: overrides.gateId ?? "G0_CONTEXT",
  title: overrides.title ?? "Sample Node",
  family: overrides.family ?? "intake_context",
  nodeType: overrides.nodeType ?? "workflow",
  authorityBoundary: overrides.authorityBoundary ?? "read_only",
  sourceStatus: overrides.sourceStatus ?? "proposed_registry_slot",
  maturity: overrides.maturity ?? "experimental",
  declaredGates: overrides.declaredGates ?? ["G0_CONTEXT"],
  purpose: overrides.purpose ?? null,
  fileReads: overrides.fileReads ?? ["AGENTS.md", "workspace.yaml"],
  fileWrites: overrides.fileWrites ?? [],
  artifacts: overrides.artifacts ?? [".gwc/tasks/TEST/context-snapshot.yaml"],
  runbook: overrides.runbook ?? ["Read AGENTS.md", "Resolve source"],
  taskControllerHistory: overrides.taskControllerHistory ?? [],
  executorHistory: overrides.executorHistory ?? [],
  checkpoints: overrides.checkpoints ?? [],
  ...overrides,
});

export const makeModel = (overrides: Partial<UnifiedRunWorkspaceModel>): UnifiedRunWorkspaceModel => ({
  runId: overrides.runId ?? "DEV-RUN-STORYBOOK-001",
  taskRef: overrides.taskRef ?? "SCRUM-820",
  mode: overrides.mode ?? "LIVE",
  status: overrides.status ?? "active",
  hierarchy: overrides.hierarchy ?? null,
  nodes: overrides.nodes ?? [makeNode({ id: "n1" }), makeNode({ id: "n2" })],
  edges: overrides.edges ?? [],
  orderedSteps: overrides.orderedSteps ?? [{ nodeId: "n1", sequence: 1 }, { nodeId: "n2", sequence: 2 }],
  currentSequence: overrides.currentSequence ?? 1,
  canonicalHistoryAvailable: overrides.canonicalHistoryAvailable ?? true,
  projectionStatus: overrides.projectionStatus ?? "RESOLVED",
  sourceDigest: overrides.sourceDigest ?? null,
});

// State variants for RuntimeNodeCard
export const NODE_STATES: Record<string, RuntimeNodeState> = {
  done: "DONE",
  active: "ACTIVE",
  future: "FUTURE",
  blocked: "BLOCKED",
  unknown: "UNKNOWN",
};

// State variants for NextFlowPanel
export const NEXTFLOW_STATES = ["RESOLVED", "UNKNOWN", "BLOCKED", "CONFLICT"] as const;

// Scenario variants for UnifiedRunWorkspace
export const SCENARIOS: Record<string, Partial<UnifiedRunWorkspaceModel>> = {
  LoginAuthSimulated: {
    runId: "DEV-RUN-LOGIN-AUTH-001",
    mode: "SIMULATED",
    status: "simulated_complete",
    nodes: [makeNode({ id: "auth-1", title: "Login Auth Check", family: "auth" })],
    orderedSteps: [{ nodeId: "auth-1", sequence: 1 }],
    currentSequence: 1,
  },
  NodeArchitectSimulated: {
    runId: "DEV-RUN-NODE-ARCH-001",
    mode: "SIMULATED",
    status: "simulated_complete",
    nodes: [makeNode({ id: "arch-1", title: "Node Architect Review", family: "node_architect" })],
    orderedSteps: [{ nodeId: "arch-1", sequence: 1 }],
    currentSequence: 1,
  },
  LiveReal: {
    runId: "DEV-RUN-LIVE-REAL-001",
    mode: "LIVE",
    status: "active",
    nodes: [makeNode({ id: "live-1", title: "Live Runtime Node", family: "runtime" })],
    orderedSteps: [{ nodeId: "live-1", sequence: 1 }],
    currentSequence: 1,
  },
  Replay: {
    runId: "DEV-RUN-REPLAY-001",
    mode: "REPLAY",
    status: "completed",
    nodes: [makeNode({ id: "replay-1", title: "Replay Node", family: "runtime" })],
    orderedSteps: [{ nodeId: "replay-1", sequence: 1 }],
    currentSequence: 1,
  },
  Degraded: {
    runId: "DEV-RUN-DEGRADED-001",
    mode: "LIVE",
    status: "degraded",
    nodes: [makeNode({ id: "deg-1", title: "Degraded Node", family: "runtime", sourceStatus: "unavailable" })],
    orderedSteps: [{ nodeId: "deg-1", sequence: 1 }],
    currentSequence: 1,
  },
  RelationConflict: {
    runId: "DEV-RUN-CONFLICT-001",
    mode: "LIVE",
    status: "conflict",
    nodes: [makeNode({ id: "conf-1", title: "Conflict Node", family: "runtime", sourceStatus: "conflict" })],
    orderedSteps: [{ nodeId: "conf-1", sequence: 1 }],
    currentSequence: 1,
  },
};