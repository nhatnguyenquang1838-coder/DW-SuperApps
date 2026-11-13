import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
const jar = vi.hoisted(() => ({ value: 'fixture' }));
vi.mock('next/headers', () => ({ cookies: () => ({ get: () => ({ value: jar.value }) }) }));
import TasksPage from '@/app/tasks/page';
import TaskRunsPage from '@/app/tasks/[taskId]/runs/page';
import RunsPage from '@/app/runs/page';
import RunDetailPage from '@/app/runs/[runId]/page';
import RunReplayPage from '@/app/runs/[runId]/replay/page';

afterEach(() => { jar.value = 'fixture'; vi.unstubAllEnvs(); });
describe('browser datasource reaches every canonical route', () => {
  it('uses cookie on tasks, task runs, run explorer, detail and replay', async () => {
    vi.stubEnv('OBSERVATORY_DATA_SOURCE', 'real');
    let view = render(await TasksPage());
    expect(screen.getByTestId('dev-fixture-indicator')).toBeTruthy();
    expect(view.container.querySelectorAll('.notion-task-card')).toHaveLength(8);
    view.unmount();
    view = render(await TaskRunsPage({ params: { taskId: 'TASK-CORE' } }));
    expect(view.container.querySelectorAll('.notion-run-card')).toHaveLength(8);
    view.unmount();
    view = render(await RunsPage());
    expect(view.container.querySelectorAll('.notion-run-card')).toHaveLength(39);
    expect(view.container.querySelector("a[href='/runs/DEMO-DELIVERY-ROOT']")).toBeTruthy();
    view.unmount();
    view = render(await RunDetailPage({ params: { runId: 'DEV-RUN-006' }, searchParams: {} }));
    expect(screen.getByTestId('dev-fixture-indicator')).toBeTruthy();
    view.unmount();
    view = render(await RunReplayPage({ params: { runId: 'DEV-RUN-001' } }));
    expect(screen.getByTestId('replay-pane')).toBeTruthy();
    view.unmount();
    jar.value = 'real';
    view = render(await TasksPage());
    expect(screen.queryByTestId('dev-fixture-indicator')).toBeNull();
    expect(view.container.textContent).toContain('No fixture data shown in real mode');
  }, 30000);
});
