// Server Component (Next.js App Router) — UnifiedRunWorkspace shell.
//
// REAL mode: reads exact stored run data through the publishable/RLS-compatible
// server path (lib/serverRunRead.readServerRunDetail). NO fixture fallback.
//
// MOCK mode (OBSERVATORY_DATA_SOURCE=mock): deterministic fixture-backed review
// path — same shell component, different data source.
//
// Both modes render through the same UnifiedRunWorkspace component tree per
// TECH_SPEC §6 — no bespoke fixture workspace.

import { notFound } from "next/navigation";
import type { ProjectionEvent } from "@/lib/live";
import {
  getRun,
  UNKNOWN,
  DAG_EDGES,
  buildHierarchy,
  SUPABASE_READINESS,
} from "@/lib/observatory";
import type { NormalizedEvent, RunView } from "@/lib/observatory";

import RootCard from "@/components/RootCard";
import DagView from "@/components/DagView";
import Timeline from "@/components/Timeline";
import EvidenceInspector from "@/components/EvidenceInspector";
import RunGraphView from "@/components/RunGraphView";
import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";

import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";
import { loginAuthScenarioAdapter } from "@/lib/runtime/adapters/loginAuthScenarioAdapter";
import { fixtureScenarioAdapter } from "@/lib/runtime/adapters/fixtureScenarioAdapter";
import { realRuntimeAdapter } from "@/lib/runtime/adapters/realRuntimeAdapter";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";
import {
  getReplaySnapshot,
  replayToModel,
  PROJECTION_UNAVAILABLE,
  REPLAY_POSITION_UNAVAILABLE,
} from "@/lib/runtime/replay";

type Json = Record<string, unknown>;
import { readServerRunDetail } from "@/lib/serverRunRead";
import type { ServerRunDetailResult } from "@/lib/serverRunRead";
import { getMockProjectionEvents, MOCK_BACKEND } from "@/lib/mockDataSource";

// Normalize actor for real-mode events the same way observatory normalizes
// fixture actors: preserve string values; for deterministic JSON objects with
// kind/id, normalize to `kind:id` rather than dropping to UNKNOWN.
function normalizeActor(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object") {
    const a = raw as Record<string, unknown>;
    const kind = typeof a.kind === "string" ? a.kind : undefined;
    const id = typeof a.id === "string" ? a.id : undefined;
    const parts = [kind, id].filter((s) => s !== undefined && s !== "");
    const joined = parts.join(":").replace(/:$/, "");
    return joined.length > 0 ? joined : UNKNOWN;
  }
  return UNKNOWN;
}

// Map a canonical ProjectionEvent to the observatory NormalizedEvent shape
// using EXACT stored values only; absent fields stay UNKNOWN (never fabricated).
function projectionToNormalized(e: ProjectionEvent): NormalizedEvent {
  return {
    sourceEventId: e.source_event_id,
    seq: typeof e.sequence === "number" ? e.sequence : null,
    occurredAt:
      typeof e.occurred_at === "string" ? (e.occurred_at as string) : UNKNOWN,
    eventType:
      typeof e.event_type === "string" ? (e.event_type as string) : UNKNOWN,
    source: e.source_system,
    actor: normalizeActor(e.actor),
    gate: typeof e.gate === "string" ? (e.gate as string) : UNKNOWN,
    nodeId: typeof e.node_id === "string" ? (e.node_id as string) : UNKNOWN,
    before: (e.before as Json) ?? {},
    after: (e.after as Json) ?? {},
    evidenceRefs: Array.isArray(e.evidence_refs)
      ? (e.evidence_refs as string[])
      : [],
    authorityRef:
      typeof e.authority_ref === "string" ? (e.authority_ref as string) : UNKNOWN,
    sourceDigest:
      typeof e.source_digest === "string" ? (e.source_digest as string) : UNKNOWN,
    annotations: {},
  };
}

// Build a RunView from the exact stored serverRunRead detail rows. Absent
// fields (lane/task/branch/...) stay UNKNOWN — never filled from fixtures.
function runViewFromDetail(
  runId: string,
  detail: ServerRunDetailResult,
): RunView {
  const run = detail.run ?? {};
  const gates: Record<string, Json> = {};
  for (const g of detail.gates) {
    if (typeof g.gate_id === "string") gates[g.gate_id as string] = g as Json;
  }
  const nodes: Record<string, Json> = {};
  for (const n of detail.nodes) {
    if (typeof n.node_id === "string") nodes[n.node_id as string] = n as Json;
  }
  const events = detail.events.map(projectionToNormalized);
  return {
    runId,
    sourceSystem:
      typeof run.source_system === "string"
        ? (run.source_system as string)
        : UNKNOWN,
    startedAt: typeof run.started_at === "string" ? (run.started_at as string) : null,
    lastEventAt: null,
    lane: UNKNOWN,
    task: UNKNOWN,
    controller: UNKNOWN,
    executor: UNKNOWN,
    branch:
      typeof run.branch === "string"
        ? (run.branch as string)
        : UNKNOWN,
    pr:
      typeof run.pr_number === "number" || typeof run.pr_number === "string"
        ? String(run.pr_number)
        : UNKNOWN,
    exactHead:
      typeof run.head_sha === "string"
        ? (run.head_sha as string)
        : UNKNOWN,
    ci:
      typeof run.ci_status === "string"
        ? (run.ci_status as string)
        : UNKNOWN,
    risk: UNKNOWN,
    blocker: UNKNOWN,
    now: UNKNOWN,
    next: UNKNOWN,
    eventCount: events.length,
    anomalyCount: 0,
    events,
    gates,
    nodes,
    anomalies: [],
  };
}

/**
 * Build a UnifiedRunWorkspaceModel from the selected data source.
 * Uses T04 adapters — never hand-crafts the model shape.
 * When replaySeq is provided, builds a REPLAY model from canonical history.
 */
async function buildWorkspaceModel(
  runId: string,
  dataSource: "mock" | "real",
  replaySeq?: number
): Promise<{ model: UnifiedRunWorkspaceModel; mode: WorkspaceMode }> {
  // ---------- REPLAY mode ----------
  if (replaySeq !== undefined && dataSource === "real") {
    const snapshot = await getReplaySnapshot(runId, replaySeq);
    if (snapshot.status === "OK" && snapshot.projection) {
      return { model: replayToModel(snapshot.projection, snapshot.selectedSequence, "REPLAY").model!, mode: "REPLAY" };
    }
    // Degraded / unavailable → fail-closed UNKNOWN model (never fixture fallback).
    const unknownModel: UnifiedRunWorkspaceModel = {
      runId,
      taskRef: null,
      mode: "REPLAY",
      status:
        snapshot.status === REPLAY_POSITION_UNAVAILABLE
          ? "REPLAY_POSITION_UNAVAILABLE"
          : "PROJECTION_UNAVAILABLE",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: snapshot.status === REPLAY_POSITION_UNAVAILABLE ? snapshot.selectedSequence : null,
      canonicalHistoryAvailable: false,
      projectionStatus:
        snapshot.status === REPLAY_POSITION_UNAVAILABLE
          ? "REPLAY_POSITION_UNAVAILABLE"
          : "PROJECTION_UNAVAILABLE",
      sourceDigest: null,
    };
    return { model: unknownModel, mode: "REPLAY" };
  }

  if (dataSource === "mock") {
    const run = getRun(runId, "mock");
    if (!run) notFound();

    // Use loginAuthScenarioAdapter with a minimal fixture built from the mock run.
    const fixture = {
      epic_id: "LOGIN-CAPABILITY" as const,
      title: (run as Record<string, unknown>).title as string ?? "Mock Run",
      run_count: 10,
      runtime_node_count: Object.values(run.gates).reduce((a: number, g: any) => a + (g.nodes?.length ?? 0), 0),
      runtime_model: "unified",
      runs: [
        {
          id: run.runId,
          index: 0,
          slug: run.runId,
          title: (run as Record<string, unknown>).title ?? "Mock Run",
          objective: (run as Record<string, unknown>).objective ?? "",
          run_kind: "implementation" as const,
          allowed_paths: [],
          forbidden_actions: [],
          gates: Object.values(run.gates).map((g: any) => ({
            id: g.id ?? g.gate_id,
            label: g.label ?? g.gate_label ?? "",
            summary: g.summary ?? "",
            x: 0, y: 0, w: 200, h: 100,
            nodes: (g.nodes ?? []).map((n: any) => ({
              gate_id: g.id ?? g.gate_id,
              id: n.id ?? n.node_id,
              title: n.title ?? n.label ?? "",
              family: n.family ?? "runtime",
              type: n.type ?? n.node_type ?? "",
              boundary: n.boundary ?? n.authority_boundary ?? "",
              purpose: n.purpose ?? "",
              fileReads: n.reads ?? n.file_reads ?? [],
              fileWrites: n.writes ?? n.file_writes ?? [],
              artifacts: n.artifacts ?? n.artifact_list ?? [],
              runbook: n.runbook ?? [],
              taskControllerHistory: n.taskControllerHistory ?? n.taskcontroller_history ?? [],
              executorHistory: n.executorHistory ?? n.executor_history ?? [],
              checkpoints: n.checkpoints ?? [],
              x: 0, y: 0, w: 100, h: 40,
            })),
            gateArtifacts: g.gate_artifacts ?? [],
            taskControllerHistory: g.taskControllerHistory ?? g.taskcontroller_history ?? [],
            executorHistory: g.executorHistory ?? g.executor_history ?? [],
          })),
          route: (run as any).route ?? Object.values(run.gates).flatMap((g: any) => (g.nodes ?? []).map((n: any, i: number) => ({ gate_id: g.id ?? g.gate_id, node_id: n.id ?? n.node_id }))),
          status: (run as Record<string, unknown>).status ?? UNKNOWN,
          summary: (run as Record<string, unknown>).summary ?? "",
        },
      ],
    };

    const model = loginAuthScenarioAdapter(fixture as any, run.runId);
    return { model: { ...model, mode: "SIMULATED" }, mode: "SIMULATED" };
  }

  // ---------------- real mode ----------------
  const detail = await readServerRunDetail(runId);
  if (detail.degraded) {
    const model: UnifiedRunWorkspaceModel = {
      runId,
      taskRef: null,
      mode: "LIVE",
      status: "UNKNOWN",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "PROJECTION_UNAVAILABLE",
      sourceDigest: null,
    };
    return { model, mode: "LIVE" };
  }

  if (!detail.run) notFound();

  const model = await realRuntimeAdapter(runId);
  return { model, mode: "LIVE" };
}

export default async function RunDetailPage({
  params,
  searchParams,
}: {
  params: { runId: string };
  searchParams: { mode?: string; seq?: string };
}) {
  const dataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  // Parse replay query params (Next.js 14.2.5 — synchronous searchParams).
  const replaySeq =
    searchParams.mode === "replay" && searchParams.seq
      ? parseInt(searchParams.seq, 10)
      : undefined;

  // Build the unified model from the selected data source.
  const { model, mode } = await buildWorkspaceModel(
    params.runId,
    dataSource,
    replaySeq
  );

  // Mock mode still renders legacy navigation context alongside the shell.
  if (dataSource === "mock") {
    const run = getRun(params.runId, "mock");
    const hierarchy = buildHierarchy(run!, "mock");
    const historicalEvents = getMockProjectionEvents(params.runId);

    return (
      <section className="space-y-8">
        {/* Unified workspace shell — all scenarios render through this */}
        <UnifiedRunWorkspace model={model} />

        {/* Legacy navigation context (preserved for mock-mode review) */}
        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--dwo-color-text-muted)" }}>
            Run Tree
          </h2>
          <RootCard run={run!} unknownSentinel={UNKNOWN} supabaseReadiness={SUPABASE_READINESS} />
          <RunGraphView hierarchy={hierarchy} />
        </div>

        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--dwo-color-text-muted)" }}>Flow</h2>
          <DagView gates={run!.gates} nodes={run!.nodes} edges={DAG_EDGES[run!.runId]} />
        </div>

        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--dwo-color-text-muted)" }}>Timeline</h2>
          <Timeline events={run!.events} unknownSentinel={UNKNOWN} />
        </div>

        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--dwo-color-text-muted)" }}>Details</h2>
          <EvidenceInspector events={run!.events} anomalies={run!.anomalies} unknownSentinel={UNKNOWN} />
        </div>

        <p className="text-xs" style={{ color: "var(--dwo-color-text-faint)" }}>
          data-source: mock · backend: {MOCK_BACKEND} · run: {run!.runId}
        </p>
      </section>
    );
  }

  // ---------------- real mode ----------------
  return (
    <section className="space-y-8">
      <UnifiedRunWorkspace model={model} />
    </section>
  );
}