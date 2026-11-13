import { test, expect } from '@playwright/test';

for (const story of ['DELIVERY', 'BLOCKED', 'RETRY']) {
  test(`inspect ${story} work, evidence, multi-event replay and every child`, async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/runs');
    await page.getByLabel('Datasource', { exact: true }).selectOption('fixture');
    const showcase = page.getByTestId('work-demo-showcase');
    await expect(showcase).toContainText('166 recorded demo events');
    await expect(page.locator('.notion-run-card')).toHaveCount(43);
    const root = `DEMO-${story}-ROOT`;
    await page.locator(`a.notion-run-card[href='/runs/${root}']`).click();
    await expect(page.getByTestId('dev-fixture-indicator')).toContainText('DWO-WORK-DEMO-V1');
    await expect(page.getByTestId('dev-fixture-taskref')).toContainText(`DEMO-TASK-${story}`);
    await expect(page.getByTestId('unified-run-workspace')).toBeVisible();
    await expect(page.getByTestId('axis-qualification')).not.toContainText('QUALIFIED');
    await page.locator('.dwo-inspector-tab[data-tab="artifacts"]').click();
    await page.locator('[data-pane="artifacts"] button').filter({ hasText: 'execution/' }).first().click();
    await expect(page.getByLabel('Artifact source content')).toContainText('"synthetic": true');
    await page.getByRole('button', { name: 'Close artifact viewer' }).click();
    await page.screenshot({ path: testInfo.outputPath(`${story.toLowerCase()}-workspace.png`) });
    await page.getByTestId('fixture-open-replay').click();
    await expect(page.getByTestId('replay-sync')).toHaveText('SYNCHRONIZED');
    await expect(page.getByTestId('root-anomaly-count')).toHaveText('0');
    const tip = await page.getByTestId('replay-cursor').innerText();
    const digest = await page.getByTestId('replay-digest').innerText();
    await expect(page.getByTestId('surface-timeline')).toContainText('Scope understood');
    if (story === 'RETRY') await expect(page.getByTestId('surface-timeline')).toContainText('Retry execution after verification failure');
    await page.getByTestId('replay-start').click();
    await expect(page.getByTestId('root-applied')).toContainText('0 of');
    await expect(page.getByTestId('surface-timeline').locator('li')).toHaveCount(0);
    await expect(page.getByTestId('replay-digest')).not.toHaveText(digest);
    await page.getByTestId('replay-forward').click();
    await expect(page.getByTestId('root-applied')).toContainText('1 of');
    await page.getByTestId('replay-tip').click();
    await expect(page.getByTestId('replay-cursor')).toHaveText(tip);
    await expect(page.getByTestId('replay-digest')).toHaveText(digest);
    await page.screenshot({ path: testInfo.outputPath(`${story.toLowerCase()}-replay.png`) });
    for (const child of ['API', 'UI']) {
      const id = `DEMO-${story}-${child}`;
      await page.goto(`/runs/${id}`);
      await expect(page.getByTestId('unified-run-workspace')).toBeVisible();
      const evidence = await page.request.get(`/dev/evidence/${id}?path=execution%2F${id}-execution.json`);
      expect(evidence.status()).toBe(200);
      const payload = await evidence.json();
      expect(JSON.parse(payload.text).run_id).toBe(id);
    }
    expect(errors).toEqual([]);
  });
}

test('showcase remains readable on a narrow screen and is absent in Real', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/runs');
  await page.getByLabel('Datasource', { exact: true }).selectOption('fixture');
  await expect(page.getByTestId('work-demo-showcase')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('work-showcase-mobile.png') });
  await page.getByLabel('Datasource', { exact: true }).selectOption('real');
  await expect(page.getByTestId('work-demo-showcase')).toHaveCount(0);
  expect((await page.request.get('/dev/evidence/DEMO-DELIVERY-ROOT?path=execution%2FDEMO-DELIVERY-ROOT-execution.json')).status()).toBe(404);
});
