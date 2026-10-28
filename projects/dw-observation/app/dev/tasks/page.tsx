/**
 * Dev Task-first preview — SERVER entry point.
 *
 * /dev/tasks lists the fixture-backed Task relation records from
 * dwo-v2/fixtures/DWO-UR-30-V1/tasks/task-relations.jsonl.
 *
 * This route is DEV-ONLY. The production /tasks route resolves through
 * lib/taskRead.resolveTask with the real adapter; it never imports this file.
 * The fixture adapter here is wired explicitly so a reviewer can see the
 * Task → Root-run relation shape without a live Jira source.
 *
 * Read-only. Grants no effect capability.
 */

import Link from 'next/link';
import { FIXTURE_TASK_RELATIONS_PATH, listFixtureTaskRelations } from '@/lib/dwo/fixtureTaskRead';
import type { TaskSummary } from '@/lib/taskTypes';

export default async function DevTasksPage() {
  const tasks: TaskSummary[] = await listFixtureTaskRelations();

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
          <span style={{ color: 'var(--dwo-color-text-muted)' }}>Dev</span> / Tasks
        </nav>
        <h1
          className="mb-1 text-2xl font-bold tracking-tight"
          style={{ color: 'var(--dwo-color-text-primary)' }}
        >
          Fixture Task Relations
        </h1>
        <p className="mb-6 text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>
          DWO-UR-30-V1 · {FIXTURE_TASK_RELATIONS_PATH} · {tasks.length} relation records
        </p>

        {tasks.length === 0 ? (
          <div
            className="rounded-md border px-4 py-3 text-sm"
            style={{
              borderColor: 'var(--dwo-color-state-amber)',
              background: 'var(--dwo-color-bg-subtle)',
              color: 'var(--dwo-color-state-amber)',
            }}
          >
            No fixture task relations found — fail closed.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="fixture-task-list">
            {tasks.map((t) => (
              <Link
                key={t.taskRef}
                href={`/dev/tasks/${encodeURIComponent(t.taskRef)}/runs`}
                className="notion-task-card block rounded-lg border p-4 transition-colors"
                style={{ color: 'inherit' }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-sm font-semibold"
                    style={{ color: 'var(--dwo-color-text-primary)' }}
                  >
                    {t.taskRef}
                  </span>
                  <span
                    className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wide"
                    style={{ background: 'var(--dwo-color-bg-subtle)', color: 'var(--dwo-color-text-muted)' }}
                  >
                    {t.status}
                  </span>
                </div>
                <p className="mt-1 text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>
                  {t.title ?? '—'}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Domain</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{t.domain ?? '—'}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Root runs</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{t.rootRunCount ?? 0}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Revision</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)' }}>{t.relationRevision ?? '—'}</dd>
                  </div>
                  <div>
                    <dt style={{ color: 'var(--dwo-color-text-faint)' }}>Latest</dt>
                    <dd style={{ color: 'var(--dwo-color-text-primary)', fontFamily: 'ui-monospace, monospace', fontSize: '10px' }}>
                      {t.latestRunId ?? '—'}
                    </dd>
                  </div>
                </dl>
              </Link>
            ))}
          </div>
        )}

        <a
          href="/dev/fixtures"
          className="notion-link-btn mt-8 inline-block rounded border px-3 py-1.5 text-sm transition-colors"
        >
          ← Back to Fixture Lab
        </a>

        <style>{`
          .notion-task-card { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-surface); }
          .notion-task-card:hover { border-color: var(--dwo-color-accent-blue); }
          .notion-link-btn { border-color: var(--dwo-color-border-default); background: var(--dwo-color-bg-subtle); color: var(--dwo-color-text-primary); }
          .notion-link-btn:hover { background: var(--dwo-color-bg-surface); }
        `}</style>
      </div>
    </div>
  );
}