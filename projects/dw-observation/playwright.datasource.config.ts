import { defineConfig } from '@playwright/test';

// Run against an already-running local development server (no deployment effects).
export default defineConfig({
  testDir: './e2e',
  testMatch: /(?:global-datasource|work-demo-fixtures)\.spec\.ts/,
  timeout: 120_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: 'list',
  outputDir: 'test-results/global-datasource',
  use: {
    baseURL: 'http://127.0.0.1:3001',
    browserName: 'chromium',
    channel: 'chrome',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
