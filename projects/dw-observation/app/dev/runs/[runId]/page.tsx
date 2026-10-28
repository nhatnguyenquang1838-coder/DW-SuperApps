/**
 * Dev Run Detail — SERVER entry point.
 *
 * /dev/runs/[runId] — fixture-backed run detail with replay + qualification.
 *
 * This is the DEV twin of /runs/[runId]. It forces OBSERVATORY_DATA_SOURCE=fixture
 * (never real) so a reviewer can navigate Task → Root Run → Replay through the
 * DWO-UR-30-V1 pack without a live source. The production route stays untouched.
 *
 * Read-only. Grants no effect capability. Never opens a LangGraph checkpointer.
 */

import UnifiedRunWorkspace from '@/components/dwo/UnifiedRunWorkspace';
import { buildWorkspaceModel } from '@/lib/runtime/buildWorkspaceModel';
import { readQualificationProjection } from '@/lib/dwo/qualificationRead';
import { loadFixtureQualificationReceipt, fixtureReceiptToProjection } from '@/lib/dwo/fixtureQualification';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import type { QualificationProjection } from '@/lib/dwo/qualificationProjection';
import Link from 'next/link';

export default async function DevRunDetailPage({
  params,
  searchParams,
}: {
  params: { runId: string };
  searchParams: { mode?: string; seq?: string };
}) {
  const runId = decodeURIComponent(params.runId);

  // Force fixture source — never fall through to real.
  const replaySeq =
    searchParams.mode === 'replay' && searchParams.seq
      ? parseInt(searchParams.seq, 10)
      : undefined;

  const { model } = await buildWorkspaceModel(runId, 'fixture', replaySeq);

  // Fixture qualification: deterministic synthetic receipt bound to the exact
  // fixture subject. Missing receipt (DEV-RUN-020) → INCOMPATIBLE, never QUALIFIED.
  const receipt = loadFixtureQualificationReceipt(runId);
  const fixtureQualification: QualificationProjection = fixtureReceiptToProjection(
    runId,
    receipt
  );

  // The production route reads from the internal GET-only qualification service.
  // In dev-fixture mode that service is unconfigured → UNKNOWN, which is correct
  // (the fixture receipt is the authoritative dev-fixture axis, kept separate).
  const serviceQualification = await readQualificationProjection(runId);

  const session = createFixtureReplaySession(runId);

  return (
    <div
      className="min-h-screen"
      style={{
        background: 'var(--dwo-color-bg-canvas)',
        color: 'var(--dwo-color-text-primary)',
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <div className="mx-auto max-w-5xl px-6 py-10">
        <nav className="mb-6 text-xs" style={{ color: 'var(--dwo-color-text-faint)' }}>
          <Link href="/dev/tasks" style={{ color: 'var(--dwo-color-text-muted)' }}>
            Dev Tasks
          </Link>{' '}
          / <span style={{ color: 'var(--dwo-color-text-muted)' }}>Runs</span>{' '}
          / <span style={{ color: 'var(--dwo-color-text-primary)' }}>{runId}</span>
        </nav>

        {/* Prominent DEV FIXTURE indicator — F4 criterion */}
        <div
          className="mb-6 flex items-center gap-3 rounded-md border px-4 py-2"
          style={{
            borderColor: 'var(--dwo-color-state-amber)',
            background: 'var(--dwo-color-bg-subtle)',
          }}
          data-testid="dev-fixture-indicator"
        >
          <span
            className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
            style={{ background: 'var(--dwo-color-state-amber)', color: 'var(--dwo-color-bg-canvas)' }}
          >
            DEV FIXTURE
          </span>
          <span className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>
            DWO-UR-30-V1 · read-only preview · not reachable from production run routes
          </span>
          <span
            className="ml-auto text-xs"
            style={{ color: 'var(--dwo-color-text-muted)' }}
            data-testid="dev-fixture-taskref"
          >
            task: <strong>{model.taskRef ?? '—'}</strong>
          </span>
        </div>

        <UnifiedRunWorkspace
          model={model}
          qualificationProjection={fixtureQualification}
        />

        {/* F2/F4: replay entry point for this run (synchronized ReplayPane). */}
        <div className="mt-6">
          {session ? (
            <Link
              href={`/dev/runs/${encodeURIComponent(runId)}/replay`}
              className="notion-link-btn inline-block rounded border px-3 py-1.5 text-sm transition-colors"
              style={{
                borderColor: 'var(--dwo-color-border-default)',
                background: 'var(--dwo-color-bg-subtle)',
                color: 'var(--dwo-color-text-primary)',
              }}
              data-testid="dev-open-replay"
            >
              Open synchronized replay → ({session.total} events)
            </Link>
          ) : (
            <p className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>
              No projection events for this run — replay UNAVAILABLE (fail-closed).
            </p>
          )}
        </div>

        <details className="mt-6 text-xs" style={{ color: 'var(--dwo-color-text-faint)' }}>
          <summary style={{ cursor: 'pointer' }}>Qualification axes (debug)</summary>
          <div className="mt-2 space-y-1">
            <div>
              <strong>Fixture receipt:</strong> status={fixtureQualification.status} ·
              reason={fixtureQualification.reasonCode} ·
              receipt={fixtureQualification.receiptId ?? '—'}
            </div>
            <div>
              <strong>Service projection:</strong> status={serviceQualification.status} ·
              reason={serviceQualification.reasonCode}
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}