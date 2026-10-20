// Data-source dispatch for the UnifiedRunWorkspace model.
//
// Extracted from app/runs/[runId]/page.tsx so it can be unit-tested WITHOUT
// exporting a non-page symbol from an App Router route: Next.js 14 forbids any
// export other than the page's own allowlist, and a stray `export` on a route
// fails `tsc` via the generated `.next/types` constraint.
//
// Routing failure stays with the route via the `onMissing` callback, so tests
// can inject a plain throw and never trigger Next's router. Production keeps
// the `notFound()` default.

import { notFound } from "next/navigation";

import { getRun, UNKNOWN } from "@/lib/observatory";
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

import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "@/lib/runtime/unifiedRuntime";

export type WorkspaceDataSource = "mock" | "real" | "fixture";

export interface BuiltWorkspace {
  model: UnifiedRunWorkspaceModel;
  mode: WorkspaceMode;
}

/**
 * Build a UnifiedRunWorkspaceModel from the selected data source.
 * Uses T04 adapters — never hand-crafts the model shape.
 * When replaySeq is provided, builds a REPLAY model from canonical history.
 *
 * Every unavailable path is fail-closed: a missing run, projection or history
 * yields an UNKNOWN / *_UNAVAILABLE model, never a fixture or mock fallback.
 */
export async function buildWorkspaceModel(
  runId: string,
  dataSource: WorkspaceDataSource,
  replaySeq?: number,
  onMissing: () => never = () => notFound()
): Promise<BuiltWorkspace> {
  // ---------- REPLAY mode ----------
  if (replaySeq !== undefined && dataSource === "real") {
    const snapshot = await getReplaySnapshot(runId, replaySeq);
    if (snapshot.status === "OK" && snapshot.projection) {
      const replayed = replayToModel(snapshot.projection, snapshot.selectedSequence, "REPLAY");
      if (replayed.model) {
        return { model: replayed.model, mode: "REPLAY" };
      }
      // status OK but no model → still fail closed below rather than fabricate.
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
  // ---------- MOCK mode ----------
  if (dataSource === "mock") {
    const run = getRun(runId, "mock");
    if (!run) return onMissing();

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
            taskControllerHistory: g.taskControllerHistory ?? [],
            executorHistory: g.executorHistory ?? [],
          })),
          route: (run as any).route ?? Object.values(run.gates).flatMap((g: any) => (g.nodes ?? []).map((n: any) => ({ gate_id: g.id ?? g.gate_id, node_id: n.id ?? n.node_id }))),
          status: (run as Record<string, unknown>).status ?? UNKNOWN,
          summary: (run as Record<string, unknown>).summary ?? "",
        },
      ],
    };

    const model = loginAuthScenarioAdapter(fixture as any, run.runId);
    return { model: { ...model, mode: "SIMULATED" } as UnifiedRunWorkspaceModel, mode: "SIMULATED" };
  }

  // ---------------- fixture mode ----------------
  if (dataSource === "fixture") {
    const entry = FIXTURE_CATALOG.find((c) => c.id === runId);
    if (!entry) return onMissing();
    const model = fixtureScenarioAdapter(entry);
    return { model: { ...model, mode: "SIMULATED" } as UnifiedRunWorkspaceModel, mode: "SIMULATED" };
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

  if (!detail.run) return onMissing();

  const model = await realRuntimeAdapter(runId);
  return { model, mode: "LIVE" };
}
