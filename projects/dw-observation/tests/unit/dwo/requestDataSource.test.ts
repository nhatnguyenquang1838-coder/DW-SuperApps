import { afterEach, describe, expect, it, vi } from 'vitest';
const jar = vi.hoisted(() => ({ value: undefined as string | undefined, set: vi.fn() }));
vi.mock('next/headers', () => ({ cookies: () => ({ get: () => jar.value ? { value: jar.value } : undefined, set: jar.set }) }));
import { getRequestDataSource } from '@/lib/dwo/requestDataSource';
import { changeDataSource } from '@/app/actions/dataSource';

afterEach(() => { jar.value = undefined; jar.set.mockReset(); vi.unstubAllEnvs(); });

describe('request-scoped datasource', () => {
  it('reads a browser cookie on every request, not dashboard module state', () => {
    vi.stubEnv('NODE_ENV', 'development');
    jar.value = 'fixture';
    expect(getRequestDataSource()).toBe('fixture');
    jar.value = 'real';
    expect(getRequestDataSource()).toBe('real');
  });
  it('explicit real overrides fixture environment and invalid cookies fail closed', () => {
    vi.stubEnv('OBSERVATORY_DATA_SOURCE', 'fixture');
    jar.value = 'real';
    expect(getRequestDataSource()).toBe('real');
    jar.value = 'invalid';
    expect(getRequestDataSource()).toBe('real');
  });
  it('cannot enable fixtures in production', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    jar.value = 'fixture';
    expect(getRequestDataSource()).toBe('real');
    await expect(changeDataSource('fixture')).rejects.toThrow(/production/);
    expect(jar.set).not.toHaveBeenCalled();
  });
  it('persists validated selection at root path for all routes', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    await changeDataSource('fixture');
    expect(jar.set).toHaveBeenCalledWith('dwo-data-source', 'fixture', expect.objectContaining({ path: '/', httpOnly: true, sameSite: 'lax' }));
    await expect(changeDataSource('bad' as 'real')).rejects.toThrow(/Invalid/);
    expect(jar.set).toHaveBeenCalledTimes(1);
  });
});
