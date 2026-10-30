import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const sourceMode = process.env.PLAYWRIGHT_SOURCE === 'mock' ? 'mock' : 'fixture';
const selectedPort = sourceMode === 'fixture'
  ? Number(process.env.PLAYWRIGHT_FIXTURE_PORT ?? 3100)
  : Number(process.env.PLAYWRIGHT_MOCK_PORT ?? 3101);
const launcher = path.resolve(process.cwd(), 'scripts/start-playwright-server.mjs');
const launchCommand = `${JSON.stringify(process.execPath)} ${JSON.stringify(launcher)} ${sourceMode} ${selectedPort}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? 'test-results',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: launchCommand,
    url: `http://localhost:${selectedPort}`,
    env: { ...process.env, PLAYWRIGHT_SOURCE: sourceMode, OBSERVATORY_DATA_SOURCE: sourceMode },
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: sourceMode === 'fixture'
    ? [{
        name: 'fixture-preview-chromium',
        testMatch: '**/fixture-preview-r1.spec.ts',
        use: { ...devices['Desktop Chrome'], baseURL: `http://localhost:${selectedPort}` },
      }]
    : [{
        name: 'mock-navigation-visual-chromium',
        testMatch: ['**/dwo-navigation.spec.ts', '**/dwo-visual.spec.ts'],
        use: { ...devices['Desktop Chrome'], baseURL: `http://localhost:${selectedPort}` },
      }],
});
