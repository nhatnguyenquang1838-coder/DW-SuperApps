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

// NOTE: this route exports ONLY `default`. Next.js 14 rejects any other export
// through the generated `.next/types` constraint, so the data-source dispatch
// lives in lib/runtime/buildWorkspaceModel.ts where it is directly unit-testable.

import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import { buildWorkspaceModel } from "@/lib/runtime/buildWorkspaceModel";

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