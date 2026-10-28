/**
 * Dev Task → Root runs — SERVER entry point.
 *
 * /dev/tasks/[taskId]/runs lists the root runs for a fixture task relation,
 * with replay + qualification projections pre-loaded on the server.
 *
 * DEV-ONLY. The production /tasks/[taskId]/runs route resolves through
 * lib/taskRead.resolveTask with the real adapter; it never imports this file.
 *
 * Read-only. Grants no effect capability.
 */

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getFixtureTaskRelation } from '@/lib/dwo/fixtureTaskRead';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import { loadFixtureQualificationReceipt, fixtureReceiptToProjection } from '@/lib/dwo/fixtureQualification';
import type { QualificationProjection } from '@/lib/dwo/qualificationProjection';
import RunStatusAxes from '@/components/dwo/RunStatusAxes';

type RunRow = {
  runId: string;
  status: string;
  sourceSystem: string | null;
  startedAt: string | null;
  totalEvents: number;
  synchronized: boolean;
  replayAvailable: boolean;
  qualification: QualificationProjection;
};

function FixtureStatusAxes({ qualification }: { qualification: QualificationProjection }) {
  return (
    <RunStatusAxes
      projectionSync="LIVE"
      view="CURRENT"
      qualification={qualification}
    />
  );
}

export default async function DevTaskRunsPage({ params }: { params: { taskId: string } }) {
  const taskRef = decodeURIComponent(params.taskId);
  const rel = await getFixtureTaskRelation(taskRef);

  if (!rel) {
    notFound();
  }

  const rows: RunRow[] = [];
  for (const runId of rel.rootRunIds) {
    const session = createFixtureReplaySession(runId);
    const receipt = loadFixtureQualificationReceipt(runId);
    const qualification = fixtureReceiptToProjection(runId, receipt);
    rows.push({
      runId,
      status: session ? 'LIVE' : 'UNAVAILABLE',
sourceSystem: 'fixture',
      startedAt: session?.frame.projection.startedAt ?? null,
      totalEvents: session?.total ?? 0,
      synchronized: session?.synchronized ?? false,
      replayAvailable: session !== null,
      qualification,
    });
  }

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
          / <span style={{ color: 'var(--dwo-color-text-primary)' }}>{taskRef}</span> / Runs
        </nav>

        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: 'var(--dwo-color-text-primary)' }}
        >
          {taskRef}
        </h1>
        <p className="mb-2 text-sm" style={{ color: 'var(--dwo-color-text-primary)' }}>
          {rel.title ?? '—'}
        </p>
        <p className="mb-6 text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>
          domain: {rel.domain ?? '—'} · relation: {rel.status} · revision:{' '}
          {rel.relationRevision ?? '—'} · source: fixture · latest:{' '}
          <span style={{ fontFamily: 'ui-monospace, monospace' }}>{rel.latestRunId ?? '—'}</span>
        </p>

        {rows.length === 0 ? (
          <div
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: 'var(--dwo-color-state-amber)',
              background: 'var(--dwo-color-bg-subtle)',
              color: 'var(--dwo-color-state-amber)',
            }}
          >
            No root runs resolved for this task — no relation record exists
            (TaskRunIndexV2 fail-closed, no run-id inference).
          </div>
        ) : (
          <div className="space-y-4">
            {rows.map((r) => (
              <div
                key={r.runId}
                className="notion-run-card block rounded-lg border p-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-sm font-semibold"
                    style={{ color: 'var(--dwo-color-text-primary)' }}
                  >
                    {r.runId}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: 'var(--dwo-color-bg-subtle)', color: 'var(--dwo-color-text-muted)' }}
                  >
                    {r.sourceSystem ?? '—'}
                  </span>
                </div>

                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Status</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{r.status}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Started</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{r.startedAt ?? '—'}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Events</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{r.totalEvents}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Synced</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{r.synchronized ? 'yes' : 'no'}</dd>
                  </div>
                </dl>

                <div className="mt-3">
                  <FixtureStatusAxes qualification={r.qualification} />
                </div>

                <div className="mt-3">
                  <a
                    href={`/dev/runs/${encodeURIComponent(r.runId)}`}
                    className="notion-link-btn inline-block rounded border px-3 py-1.5 text-sm transition-colors"
                  >
                    Open replay →
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}

        <a
          href="/dev/tasks"
          className="notion-link-btn mt-8 inline-block rounded border px-3 py-1.5 text-sm transition-colors"
        >
          ← Back to tasks
        </a>

        <style>{`
          .notion-run-card { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-surface); }
          .notion-link-btn { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-subtle); color: var(--dwo-color-text-primary); }
          .notion-link-btn:hover { background: var(--dwo-color-bg-surface); }
        `}</style>
      </div>
    </div>
  );
}