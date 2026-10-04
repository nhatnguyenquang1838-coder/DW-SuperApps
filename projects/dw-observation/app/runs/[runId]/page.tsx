// Server Component (Next.js App Router) — UnifiedRunWorkspace shell.
//
// REAL mode: reads exact stored run data through the publishable/RLS-compatible
// server path (lib/serverRunRead.readServerRunDetail). NO fixture fallback.
//
// MOCK mode (OBSERVATORY_DATA_SOURCE=mock): deterministic fixture-backed review
// path — same shell component, different data source.
//
// FIXTURE mode (OBSERVATORY_DATA_SOURCE=fixture): DWO-UR-30-V1 catalog-backed
// review path via fixtureScenarioAdapter.
//
// Both modes render through the same UnifiedRunWorkspace component tree per
// TECH_SPEC §6 — no bespoke fixture workspace, no legacy duplicate UI.

import { notFound } from "next/navigation";
import { getRun, UNKNOWN } from "@/lib/observatory";

import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";

import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";
import { loginAuthScenarioAdapter } from "@/lib/runtime/adapters/loginAuthScenarioAdapter";
import { realRuntimeAdapter } from "@/lib/runtime/adapters/realRuntimeAdapter";
import { fixtureScenarioAdapter } from "@/lib/runtime/adapters/fixtureScenarioAdapter";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";

import { readServerRunDetail } from "@/lib/serverRunRead";
import {
  getReplaySnapshot,
  replayToModel,
  REPLAY_POSITION_UNAVAILABLE,
} from "@/lib/runtime/replay";

/**
 * Build a UnifiedRunWorkspaceModel from the selected data source.
 * Uses T04 adapters — never hand-crafts the model shape.
 * When replaySeq is provided, builds a REPLAY model from canonical history.
 */
export async function buildWorkspaceModel(
  runId: string,
  dataSource: "mock" | "real" | "fixture",
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

  // ---------------- fixture mode ----------------
  if (dataSource === "fixture") {
    const entry = FIXTURE_CATALOG.find((c) => c.id === runId);
    if (!entry) notFound();
    const model = fixtureScenarioAdapter(entry);
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
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock"
    : process.env.OBSERVATORY_DATA_SOURCE === "fixture" ? "fixture"
    : "real";

  // Parse replay query params (Next.js 14.2.5 — synchronous searchParams).
  const replaySeq =
    searchParams.mode === "replay" && searchParams.seq
      ? parseInt(searchParams.seq, 10)
      : undefined;

  // Build the unified model from the selected data source.
  const { model } = await buildWorkspaceModel(
    params.runId,
    dataSource,
    replaySeq
  );

  // ---------------- unified workspace — single render, both modes ----------------
  return (
    <section className="space-y-8">
      <UnifiedRunWorkspace model={model} />
    </section>
  );
}