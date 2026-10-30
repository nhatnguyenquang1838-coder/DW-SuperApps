/**
 * Dev Run Replay — SERVER entry point.
 *
 * /dev/runs/[runId]/replay — fixture-backed replay pane driven by
 * FixtureReplaySession over the DWO-UR-30-V1 projection-events.jsonl.
 *
 * This is the DEV twin of /runs/[runId]/replay. It renders the synchronized
 * ReplayPane (5 surfaces: RootCard, DAG, timeline, CI/evidence, inspector) from
 * a single ReplaySession cursor — panes cannot drift because they are not
 * computed independently.
 *
 * DEV-ONLY. The production replay route resolves through readHistoricalEvents
 * with the real adapter; it never imports this file.
 *
 * Read-only. Grants no effect capability. Never opens a LangGraph checkpointer.
 * Never mutates projection_events.
 */

import { notFound } from 'next/navigation';
import Link from 'next/link';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import { loadFixtureQualificationReceipt, fixtureReceiptToProjection } from '@/lib/dwo/fixtureQualification';
import { deriveCurrentFixtureSubjectDigest } from '@/lib/dwo/currentFixtureSubject';
import ReplayPane from '@/components/ReplayPane';
import type { ProjectionEvent } from '@/lib/live';
import type { QualificationProjection } from '@/lib/dwo/qualificationProjection';
import RunStatusAxes from '@/components/dwo/RunStatusAxes';
import { isLocalFixturePreview } from '@/lib/dwo/fixturePreviewMode';

export default async function DevRunReplayPage({ params }: { params: { runId: string } }) {
  const runBasePath = isLocalFixturePreview() ? '/runs' : '/dev/runs';
  const taskBasePath = isLocalFixturePreview() ? '/tasks' : '/dev/tasks';
  const runId = decodeURIComponent(params.runId);
  const session = createFixtureReplaySession(runId);

  if (!session) {
    notFound();
  }

  const events: ProjectionEvent[] = [...session.events];
  const receipt = loadFixtureQualificationReceipt(runId);
  const qualification: QualificationProjection = fixtureReceiptToProjection(
    runId,
    receipt,
    deriveCurrentFixtureSubjectDigest(runId),
  );

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
          <Link href={taskBasePath} style={{ color: 'var(--dwo-color-text-muted)' }}>
            Dev Tasks
          </Link>{' '}
          / <span style={{ color: 'var(--dwo-color-text-muted)' }}>Runs</span>{' '}
          <Link href={`${runBasePath}/${encodeURIComponent(runId)}`} style={{ color: 'var(--dwo-color-text-muted)' }}>
            {runId}
          </Link>{' '}
          / <span style={{ color: 'var(--dwo-color-text-primary)' }}>Replay</span>
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
            DWO-UR-30-V1 · synchronized replay · not reachable from production run routes
          </span>
        </div>

        <div className="mb-6">
          <RunStatusAxes
            projectionSync="LIVE"
            view="REPLAY"
            qualification={qualification}
          />
        </div>

        <ReplayPane runId={runId} events={events} />

        <div className="mt-6">
          <Link
            href={`${runBasePath}/${encodeURIComponent(runId)}`}
            className="notion-link-btn inline-block rounded border px-3 py-1.5 text-sm transition-colors"
            style={{ borderColor: 'var(--dwo-color-border-default)', background: 'var(--dwo-color-bg-subtle)', color: 'var(--dwo-color-text-primary)' }}
          >
            ← Back to run detail
          </Link>
        </div>

        <style>{`
          .notion-link-btn:hover { background: var(--dwo-color-bg-surface); }
        `}</style>
      </div>
    </div>
  );
}