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
import { isLocalFixturePreview } from "@/lib/dwo/fixturePreviewMode";
import { readQualificationProjection } from "@/lib/dwo/qualificationRead";
import { loadFixtureQualificationReceipt, fixtureReceiptToProjection } from "@/lib/dwo/fixtureQualification";
import { createFixtureReplaySession } from "@/lib/dwo/fixtureReplaySession";
import type { QualificationProjection } from "@/lib/dwo/qualificationProjection";
import Link from "next/link";

export default async function RunDetailPage({
  params,
  searchParams,
}: {
  params: { runId: string };
  searchParams: { mode?: string; seq?: string };
}) {
  const fixtureMode = isLocalFixturePreview();
  const dataSource =
    fixtureMode ? "fixture"
    : process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock"
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

  const qualificationProjection: QualificationProjection = fixtureMode
    ? fixtureReceiptToProjection(
        params.runId,
        loadFixtureQualificationReceipt(params.runId),
      )
    : await readQualificationProjection(params.runId);
  const fixtureReplay = fixtureMode ? createFixtureReplaySession(params.runId) : null;

  // ---------------- unified workspace — single render, both modes ----------------
  return (
    <section className="space-y-8">
      {fixtureMode && (
        <div
          className="flex items-center gap-3 rounded-md border px-4 py-2"
          style={{ borderColor: 'var(--dwo-color-state-amber)', background: 'var(--dwo-color-bg-subtle)' }}
          data-testid="dev-fixture-indicator"
        >
          <strong className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest" style={{ background: 'var(--dwo-color-state-amber)', color: 'var(--dwo-color-bg-canvas)' }}>DEV FIXTURE</strong>
          <span className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>DWO-UR-30-V1 · read-only local preview · production remains real/fail-closed</span>
          <span className="ml-auto text-xs" style={{ color: 'var(--dwo-color-text-muted)' }} data-testid="dev-fixture-taskref">
            task: <strong>{model.taskRef ?? '—'}</strong>
          </span>
        </div>
      )}
      <UnifiedRunWorkspace
        model={model}
        qualificationProjection={qualificationProjection}
      />
      {fixtureMode && (
        <div>
          {fixtureReplay ? (
            <Link
              href={`/runs/${encodeURIComponent(params.runId)}/replay`}
              className="inline-block rounded border px-3 py-1.5 text-sm"
              style={{ borderColor: 'var(--dwo-color-border-default)', background: 'var(--dwo-color-bg-subtle)', color: 'var(--dwo-color-text-primary)' }}
              data-testid="fixture-open-replay"
            >
              Open fixture replay → ({fixtureReplay.total} events)
            </Link>
          ) : (
            <span data-testid="fixture-replay-unavailable" className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>
              Replay UNAVAILABLE — incompatible or no canonical fixture history.
            </span>
          )}
        </div>
      )}
    </section>
  );
}