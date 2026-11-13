import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { NextRequest } from 'next/server';
import { createDevRouteMiddleware } from '@/middleware';
const calls = vi.hoisted(() => ({ change: vi.fn(), refresh: vi.fn() }));
vi.mock('@/app/actions/dataSource', () => ({ changeDataSource: calls.change }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: calls.refresh }) }));
import DataSourceSelector from '@/components/dwo/DataSourceSelector';

it('keeps the switch disabled while the cookie action is unresolved', async () => {
  let finish!: () => void;
  calls.change.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
  render(<DataSourceSelector source="real" fixtureAllowed />);
  const select = screen.getByLabelText('Datasource') as HTMLSelectElement;
  fireEvent.change(select, { target: { value: 'fixture' } });
  expect(select.disabled).toBe(true);
  expect(screen.getByRole('status').textContent).toContain('Switching');
  await act(async () => { finish(); });
  expect(calls.refresh).toHaveBeenCalledTimes(1);
});

describe('dev fixture ingress follows browser preference', () => {
  const guard = createDevRouteMiddleware({ NODE_ENV: 'development', OBSERVATORY_DATA_SOURCE: 'fixture' });
  it.each(['/dev/tasks', '/dev/fixtures', '/dev/runs/DEV-RUN-001', '/dev/runs/DEV-RUN-001/replay'])('rejects %s with explicit Real cookie', (path) => {
    expect(guard(new NextRequest(`http://localhost${path}`, { headers: { cookie: 'dwo-data-source=real' } }))?.status).toBe(404);
  });
  it('allows fixture cookie and rejects unset default Real', () => {
    expect(guard(new NextRequest('http://localhost/dev/tasks', { headers: { cookie: 'dwo-data-source=fixture' } }))).toBeNull();
    const defaultGuard = createDevRouteMiddleware({ NODE_ENV: 'development' });
    expect(defaultGuard(new NextRequest('http://localhost/dev/tasks'))?.status).toBe(404);
  });
});
