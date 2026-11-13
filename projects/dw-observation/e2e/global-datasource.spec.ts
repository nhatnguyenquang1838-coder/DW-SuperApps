import { test, expect } from '@playwright/test';

test('datasource persists across the application and reload without leaking to another browser', async ({ page, browser }, testInfo) => {
  await page.goto('/dashboard');
  await expect(page.getByLabel('Datasource', { exact: true })).toHaveValue('real');
  // Prefetch/visit the real route before the switch to catch stale router cache.
  await page.getByRole('link', { name: 'Run Explorer', exact: true }).click();
  await expect(page.getByTestId('list-data-source-badge')).toContainText('real');
  await page.getByLabel('Datasource', { exact: true }).selectOption('fixture');
  await expect(page.getByTestId('global-data-source')).toContainText('DEV FIXTURE');
  await expect(page.locator('.notion-run-card')).toHaveCount(30);
  await page.screenshot({ path: testInfo.outputPath('fixture-run-explorer.png') });
  await page.getByRole('link', { name: 'Tasks', exact: true }).first().click();
  await expect(page.locator('.notion-task-card')).toHaveCount(5);
  await page.locator('.notion-task-card').filter({ hasText: 'TASK-CORE' }).click();
  await expect(page.locator('.notion-run-card')).toHaveCount(8);
  await page.getByTestId('view-details-DEV-RUN-001').click();
  await expect(page.getByTestId('unified-run-workspace')).toBeVisible();
  await expect(page.getByTestId('dev-fixture-indicator')).toBeVisible();
  const evidencePath = '/dev/evidence/DEV-RUN-001?path=execution%2FDEV-RUN-001-execution.json';
  const evidence = await page.request.get(evidencePath);
  expect(evidence.status()).toBe(200);
  expect((await evidence.json()).ok).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Datasource', { exact: true })).toHaveValue('fixture');
  await page.locator('[data-testid="fixture-open-replay"]').click();
  await expect(page.getByTestId('replay-pane')).toBeVisible();
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page.locator('main [data-source="fixture"]')).toBeVisible();
  await expect(page.locator('.dwo-dashboard-card').filter({ hasText: 'Tasks' }).locator('.dwo-dashboard-value')).toHaveText('5');
  const isolated = await browser.newContext();
  const separatePage = await isolated.newPage();
  await separatePage.goto('http://127.0.0.1:3001/tasks');
  await expect(separatePage.getByLabel('Datasource', { exact: true })).toHaveValue('real');
  await expect(separatePage.getByTestId('dev-fixture-indicator')).toHaveCount(0);
  await isolated.close();
  await page.getByLabel('Datasource', { exact: true }).selectOption('real');
  await expect(page.getByTestId('global-data-source')).toContainText('REAL');
  expect((await page.request.get(evidencePath)).status()).toBe(404);
  for (const path of ['/dev/tasks', '/dev/fixtures', '/dev/runs/DEV-RUN-001', '/dev/runs/DEV-RUN-001/replay']) {
    expect((await page.request.get(path)).status()).toBe(404);
  }
  await page.getByRole('link', { name: 'Tasks', exact: true }).first().click();
  await expect(page.getByTestId('dev-fixture-indicator')).toHaveCount(0);
  await expect(page.getByText(/No fixture data shown in real mode/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Datasource', { exact: true })).toHaveValue('real');
});
