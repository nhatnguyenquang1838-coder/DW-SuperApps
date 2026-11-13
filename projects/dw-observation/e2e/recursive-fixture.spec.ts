import { test, expect } from '@playwright/test';

test('recursive ROOT -> CHILD -> ATOMIC replays G0–G6 in the actual graph and independent parent transitions', async ({ page }, testInfo) => {
  const root = 'DEMO-RECURSIVE-ROOT';
  const child = 'DEMO-RECURSIVE-CHILD';
  const atoms = ['DEMO-RECURSIVE-API', 'DEMO-RECURSIVE-UI'];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/runs');
  await page.getByLabel('Datasource', { exact: true }).selectOption('fixture');
  await page.getByTestId('recursive-scenario-entry').getByRole('link').click();
  await expect(page.getByTestId('recursive-fixture-playback')).toBeVisible();
  await expect(page.getByTestId('recursive-position')).toHaveText('1/60 · G0 / ACTIVE · OPEN');
  await expect(page.locator(`.react-flow__node[data-id='${root}']`)).toContainText('ACTIVE');
  await expect(page.getByTestId(`gate-${root}-G6`)).toHaveText('NOT OBSERVED');
  await expect(page.getByRole('tree', { name: 'Run hierarchy' })).toContainText(child);
  for (const id of atoms) await expect(page.getByRole('tree', { name: 'Run hierarchy' })).toContainText(id);
  const startDigest = await page.getByTestId('recursive-state-digest').innerText();
  await page.screenshot({ path: testInfo.outputPath('recursive-g0.png'), fullPage: true });
  // The existing workspace's next control must update both graph and gate table.
  await page.getByRole('button', { name: 'Next step', exact: true }).click();
  await expect(page.getByTestId(`gate-${root}-G0`)).toHaveText('PASSED');
  await expect(page.locator(`.react-flow__node[data-id='${root}']`)).toContainText('PASSED');
  await page.getByRole('button', { name: 'Atomics complete', exact: true }).click();
  await expect(page.getByTestId(`state-${root}`)).toHaveText('OPEN');
  await expect(page.getByTestId(`gate-${root}-G2`)).toHaveText('WAITING');
  await expect(page.getByTestId(`gate-${child}-G2`)).toHaveText('WAITING');
  for (const id of atoms) await expect(page.getByTestId(`state-${id}`)).toHaveText('ACCEPTED');
  await expect(page.locator(`.react-flow__node[data-id='${root}']`)).toContainText('WAITING');
  await page.screenshot({ path: testInfo.outputPath('recursive-atomics-done-parent-waiting.png'), fullPage: true });
  await page.getByRole('button', { name: 'Child complete', exact: true }).click();
  await expect(page.getByTestId(`state-${child}`)).toHaveText('ACCEPTED');
  await expect(page.getByTestId(`state-${root}`)).toHaveText('OPEN');
  await expect(page.getByTestId(`gate-${root}-G2`)).toHaveText('WAITING');
  await page.getByRole('button', { name: 'Root G6 accepted', exact: true }).click();
  await expect(page.getByTestId('recursive-position')).toHaveText('60/60 · G6 / PASSED · ACCEPTED');
  for (const id of [root, child, ...atoms]) {
    for (const gate of ['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6']) await expect(page.getByTestId(`gate-${id}-${gate}`)).toHaveText('PASSED');
    const response = await page.request.get(`/dev/evidence/${id}?path=execution%2F${id}-execution.json`);
    expect(response.status()).toBe(200);
    expect(JSON.parse((await response.json()).text).run_id).toBe(id);
  }
  await page.locator('.dwo-inspector-tab[data-tab="artifacts"]').click();
  await page.locator('[data-pane="artifacts"] button').filter({ hasText: 'execution/' }).first().click();
  await expect(page.getByLabel('Artifact source content')).toContainText('"synthetic": true');
  await page.getByRole('button', { name: 'Close artifact viewer' }).click();
  await page.screenshot({ path: testInfo.outputPath('recursive-g6-accepted.png'), fullPage: true });
  await page.getByRole('button', { name: 'Start at G0', exact: true }).click();
  await expect(page.getByTestId('recursive-state-digest')).toHaveText(startDigest);
  await expect(page.locator('[data-pane="artifacts"] button')).toHaveCount(0);
  await expect(page.getByTestId('recursive-event-history').locator('li')).toHaveCount(1);
  // Direct replay and query-cut links retain the same workspace behavior.
  await page.goto(`/runs/${root}?mode=replay&seq=40`);
  await expect(page.getByTestId('recursive-position')).toHaveText('40/60 · G2 / WAITING · OPEN');
  await page.goto(`/runs/${root}/replay`);
  await expect(page.getByTestId('recursive-position')).toHaveText('1/60 · G0 / ACTIVE · OPEN');
  await page.getByLabel('Datasource', { exact: true }).selectOption('real');
  await expect(page.getByTestId('recursive-fixture-playback')).toHaveCount(0);
  expect((await page.request.get(`/dev/evidence/${root}?path=execution%2F${root}-execution.json`)).status()).toBe(404);
  expect(errors).toEqual([]);
});
