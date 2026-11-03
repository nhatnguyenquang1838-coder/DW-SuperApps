import { describe, expect, it, vi } from 'vitest';
import config from '../../../playwright.config';

describe('Playwright launch configuration', () => {
  it('starts only the default fixture server, with explicit mode, cold start and configurable output', () => {
    const servers = Array.isArray(config.webServer) ? config.webServer : [config.webServer];
    expect(servers).toHaveLength(1);
    expect(servers[0]?.env?.OBSERVATORY_DATA_SOURCE).toBe('fixture');
    expect(servers[0]?.reuseExistingServer).toBe(false);
    expect(servers[0]?.url).toBe('http://localhost:3100');
    expect(servers[0]?.command).toContain('start-playwright-server.mjs');
    expect(config.projects?.map((project) => project.name)).toEqual(['fixture-preview-chromium']);
    expect(config.outputDir).toBe(process.env.PLAYWRIGHT_OUTPUT_DIR ?? 'test-results');
  });

  it('selects only the mock server and its project when mock mode is explicit', async () => {
    const originalSource = process.env.PLAYWRIGHT_SOURCE;
    process.env.PLAYWRIGHT_SOURCE = 'mock';
    try {
      vi.resetModules();
      const { default: mockConfig } = await import('../../../playwright.config');
      const servers = Array.isArray(mockConfig.webServer) ? mockConfig.webServer : [mockConfig.webServer];
      expect(servers).toHaveLength(1);
      expect(servers[0]?.env?.OBSERVATORY_DATA_SOURCE).toBe('mock');
      expect(servers[0]?.url).toBe('http://localhost:3101');
      expect(mockConfig.projects?.map((project) => project.name)).toEqual(['mock-navigation-visual-chromium']);
    } finally {
      if (originalSource === undefined) delete process.env.PLAYWRIGHT_SOURCE;
      else process.env.PLAYWRIGHT_SOURCE = originalSource;
      vi.resetModules();
    }
  });
});
