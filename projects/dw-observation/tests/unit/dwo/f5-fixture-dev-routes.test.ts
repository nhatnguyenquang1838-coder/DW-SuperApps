/**
 * F5-2 — Dev Task-first preview routes.
 *
 * Verifies the DEV-ONLY routes (/dev/tasks, /dev/tasks/[taskId]/runs) wire the
 * fixture adapters correctly and that production routes never import them.
 *
 * Coverage:
 *   - /dev/tasks lists all 5 fixture task relations
 *   - /dev/tasks/[taskId]/runs resolves each task's root runs and renders
 *     replay + qualification projections
 *   - DEV-RUN-020 has no receipt → UNKNOWN (INCOMPATIBLE_SOURCE)
 *   - the fixture adapter grants no effect capability
 *   - production /tasks routes do not import the fixture adapter
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import DevTasksPage from '@/app/dev/tasks/page';
import DevTaskRunsPage from '@/app/dev/tasks/[taskId]/runs/page';
import DevRunDetailPage from '@/app/dev/runs/[runId]/page';
import { listFixtureTaskRelations, getFixtureTaskRelation, FIXTURE_TASK_CAPABILITIES } from '@/lib/dwo/fixtureTaskRead';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import { loadFixtureQualificationReceipt } from '@/lib/dwo/fixtureQualification';
import { NextRequest } from 'next/server';
import { createDevRouteMiddleware, middleware } from '@/middleware';
import * as workspaceModelModule from '@/lib/runtime/buildWorkspaceModel';
import * as replaySessionModule from '@/lib/dwo/fixtureReplaySession';
import * as currentSubjectModule from '@/lib/dwo/currentFixtureSubject';
import { isValidElement } from 'react';
import { vi } from 'vitest';

describe('F5-2 dev task-first preview routes', () => {
  it('returns 404 for every /dev route in production even when fixture mode is selected', async () => {
    const middleware = createDevRouteMiddleware({ NODE_ENV: 'production', OBSERVATORY_DATA_SOURCE: 'fixture' });
    const response = await middleware(new NextRequest('http://localhost/dev/runs/DEV-RUN-006'));
    expect(response?.status).toBe(404);
  });

  it('production middleware denies /dev routes even when fixture mode is selected', async () => {
    const previousSource = process.env.OBSERVATORY_DATA_SOURCE;
    vi.stubEnv('NODE_ENV', 'production');
    process.env.OBSERVATORY_DATA_SOURCE = 'fixture';
    try {
      for (const url of [
        'http://localhost/dev',
        'http://localhost/dev/tasks',
        'http://localhost/dev/runs/DEV-RUN-006?mode=replay',
      ]) {
        const response = middleware(new NextRequest(url));
        expect(response?.status).toBe(404);
      }
    } finally {
      vi.unstubAllEnvs();
      if (previousSource === undefined) delete process.env.OBSERVATORY_DATA_SOURCE;
      else process.env.OBSERVATORY_DATA_SOURCE = previousSource;
    }
  });

  it('allows non-production /dev fixture routes and leaves canonical paths alone', async () => {
    const middleware = createDevRouteMiddleware({ NODE_ENV: 'development', OBSERVATORY_DATA_SOURCE: 'fixture' });
    expect(await middleware(new NextRequest('http://localhost/dev/fixtures'))).toBeNull();
    expect(await middleware(new NextRequest('http://localhost/runs/DEV-RUN-006'))).toBeNull();
  });

  it('listFixtureTaskRelations returns all 5 fixture task relations', async () => {
    const tasks = await listFixtureTaskRelations();
    expect(tasks.length).toBe(5);
    const refs = tasks.map((t) => t.taskRef).sort();
    expect(refs).toEqual([
      'TASK-CORE', 'TASK-EVENT', 'TASK-PARTY', 'TASK-RESEARCH', 'TASK-WEDDING',
    ]);
  });

  it('getFixtureTaskRelation resolves a known task and returns null for unknown', async () => {
    const core = await getFixtureTaskRelation('TASK-CORE');
    expect(core).not.toBeNull();
    expect(core!.rootRunIds.length).toBe(8);

    const missing = await getFixtureTaskRelation('TASK-NOT-REAL');
    expect(missing).toBeNull();
  });

  it('createFixtureReplaySession loads events for every compatible root run', async () => {
    const tasks = await listFixtureTaskRelations();
    for (const t of tasks) {
      for (const runId of t.rootRunIds) {
        const session = createFixtureReplaySession(runId);
        if (runId === 'DEV-RUN-020') {
          expect(session, 'incompatible negative must not receive a replay session').toBeNull();
          continue;
        }
        expect(session, `replay session for ${runId}`).not.toBeNull();
        expect(session!.total).toBeGreaterThan(0);
        expect(session!.synchronized).toBe(true);
      }
    }
  });

  it('loadFixtureQualificationReceipt returns null for DEV-RUN-020 (fail closed)', () => {
    expect(loadFixtureQualificationReceipt('DEV-RUN-020')).toBeNull();
  });

  it('loadFixtureQualificationReceipt returns a receipt for every other run', () => {
    for (let i = 1; i <= 30; i++) {
      const runId = `DEV-RUN-${String(i).padStart(3, '0')}`;
      if (runId === 'DEV-RUN-020') continue;
      const r = loadFixtureQualificationReceipt(runId);
      expect(r, `receipt for ${runId}`).not.toBeNull();
    }
  });

  it('fixture adapter grants read-only access; no effect capability', () => {
    expect(FIXTURE_TASK_CAPABILITIES.read).toBe(true);
    expect(FIXTURE_TASK_CAPABILITIES.write).toBe(false);
    expect(FIXTURE_TASK_CAPABILITIES.approve).toBe(false);
    expect(FIXTURE_TASK_CAPABILITIES.deny).toBe(false);
    expect(FIXTURE_TASK_CAPABILITIES.merge).toBe(false);
    expect(FIXTURE_TASK_CAPABILITIES.deploy).toBe(false);
  });

  it('DevTasksPage renders the fixture task list', async () => {
    const { container } = render(await DevTasksPage());
    expect(container.querySelector('[data-testid="fixture-task-list"]')).toBeTruthy();
    expect(screen.getByText('Fixture Task Relations')).toBeTruthy();
    expect(screen.getByText('TASK-CORE')).toBeTruthy();
    expect(screen.getByText('TASK-WEDDING')).toBeTruthy();
  });

  it('DevTaskRunsPage renders root runs with qualification axes', async () => {
    const { container } = render(
      await DevTaskRunsPage({ params: { taskId: 'TASK-CORE' } }),
    );
    expect(screen.getByRole('heading', { name: 'TASK-CORE' })).toBeTruthy();
    expect(container.querySelector('[data-testid="axis-qualification"]')).toBeTruthy();
    // TASK-CORE owns DEV-RUN-001..020; DEV-RUN-020 has no receipt (INCOMPATIBLE).
    expect(screen.getAllByText('DEV-RUN-001').length).toBeGreaterThan(0);
    expect(screen.getAllByText('DEV-RUN-020').length).toBeGreaterThan(0);
  });

  it('DEV-RUN-020 remains unavailable and has no replay link in Task-first navigation', async () => {
    const { container } = render(
      await DevTaskRunsPage({ params: { taskId: 'TASK-CORE' } }),
    );
    const negative = [...container.querySelectorAll('.notion-run-card')]
      .find((card) => card.textContent?.includes('DEV-RUN-020'));
    expect(negative).toBeTruthy();
    expect(negative?.textContent).toContain('UNAVAILABLE');
    expect(negative?.textContent).toContain('Projection SyncDEGRADED');
    expect(negative?.textContent).not.toContain('Projection SyncLIVE');
    expect(negative?.querySelector('a[href*="DEV-RUN-020"]')).toBeNull();
  });

  it.each([
    { digest: null, status: 'UNKNOWN', reason: 'CURRENT_SUBJECT_UNAVAILABLE' },
    { digest: `sha256:${'e'.repeat(64)}`, status: 'DRIFTED', reason: 'SUBJECT_OR_GRAPH_VERSION_DRIFT' },
  ])('DevRunDetailPage passes independent current-subject $status into the workspace', async ({ digest, status, reason }) => {
    // Route wiring unit test; default committed-source integrity is tested separately.
    const subjectSpy = vi.spyOn(currentSubjectModule, 'deriveCurrentFixtureSubjectDigest').mockReturnValue(digest);
    const buildSpy = vi.spyOn(workspaceModelModule, 'buildWorkspaceModel');
    const replaySpy = vi.spyOn(replaySessionModule, 'createFixtureReplaySession').mockReturnValue(null);
    try {
      const tree = await DevRunDetailPage({
        params: { runId: 'DEV-RUN-006' },
        searchParams: {},
      });
      const findProjection = (node: unknown): Record<string, unknown> | null => {
        if (Array.isArray(node)) {
          for (const child of node) {
            const found = findProjection(child);
            if (found) return found;
          }
        } else if (isValidElement(node)) {
          const props = node.props as Record<string, unknown>;
          if (props.qualificationProjection && typeof props.qualificationProjection === 'object') {
            return props.qualificationProjection as Record<string, unknown>;
          }
          return findProjection(props.children);
        }
        return null;
      };
      const projection = findProjection(tree);
      expect(subjectSpy).toHaveBeenCalledWith('DEV-RUN-006');
      expect(buildSpy).toHaveBeenCalledWith('DEV-RUN-006', 'fixture', undefined);
      expect(projection?.status).toBe(status);
      expect(projection?.reasonCode).toBe(reason);
      expect(projection?.subjectDigest).toBe(digest);
      expect(projection?.receiptSubjectDigest).toBeTruthy();
      expect(projection?.authorityGranted).toBe(false);
      expect(projection?.projectionEventsMutated).toBe(false);
    } finally {
      subjectSpy.mockRestore();
      buildSpy.mockRestore();
      replaySpy.mockRestore();
    }
  });

  it('production /tasks routes do not import the fixture adapter', () => {
    // The production route must resolve through the real adapter only.
    const root = process.cwd();
    const prodRoute = readFileSync(join(root, 'app', 'tasks', 'page.tsx'), 'utf-8');
    expect(prodRoute).not.toContain('fixtureTaskRead');
    expect(prodRoute).toContain('readRealSummaries');

    const prodRunsRoute = readFileSync(
      join(root, 'app', 'tasks', '[taskId]', 'runs', 'page.tsx'),
      'utf-8',
    );
    expect(prodRunsRoute).not.toContain('fixtureTaskRead');
    expect(prodRunsRoute).toContain('resolveTask');
  });
});