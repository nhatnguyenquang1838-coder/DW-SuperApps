import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const evidenceDir = resolve(process.env.PLAYWRIGHT_EVIDENCE_DIR ?? resolve(process.cwd(), '../../.preview-evidence/playwright-r1'));
mkdirSync(evidenceDir, { recursive: true });

test.describe("DWO Fixture Preview R1 — Playwright evidence", () => {
  test("Task-first screen is explicitly fixture-backed", async ({ page }) => {
    await page.goto("/tasks");
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("dev-fixture-indicator")).toContainText("DEV FIXTURE");
    await expect(page.locator(".notion-task-card")).toHaveCount(5);
    await expect(page.locator("a[href='/tasks/TASK-CORE/runs']")).toBeVisible();
    await page.screenshot({ path: resolve(evidenceDir, "task-first-screen.png"), fullPage: true });
  });

  test("Fixture Lab replay supports arrival, catch-up, rewind and mode switch", async ({ page }) => {
    await page.goto("/dev/fixtures");
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".dwo-fixture-btn")).toHaveCount(30);
    await expect(page.getByTestId("fixture-replay-cursor")).toHaveText("0/0");

    await page.getByTestId("fixture-event-arrive").click();
    await expect(page.getByTestId("fixture-replay-cursor")).toHaveText("1/1");
    await page.getByTestId("fixture-catch-up").click();
    await expect(page.getByTestId("fixture-replay-cursor")).toHaveText("4/4");

    await page.getByTestId("fixture-mode-replay").click();
    await page.getByTestId("fixture-replay-start").click();
    await page.getByTestId("fixture-replay-forward").click();
    await page.getByTestId("fixture-replay-forward").click();
    await expect(page.getByTestId("fixture-replay-mode")).toHaveText("REPLAY");
    await expect(page.getByTestId("fixture-replay-cursor")).toHaveText("2/4");
    await expect(page.getByTestId("fixture-replay-sync")).toHaveText("SYNCHRONIZED");

    await page.getByTestId("fixture-replay-controls").scrollIntoViewIfNeeded();
    await page.getByTestId("fixture-replay-controls").screenshot({
      path: resolve(evidenceDir, "fixture-lab-replay-controls.png"),
    });
  });

  test("Shared workspace player, recursive tree and inspector follow one prefix", async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/dev/fixtures');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('fixture-catalog').getByRole('button', { name: /DEV-RUN-017/ }).click();
    await expect(page.getByTestId('node-inspector')).toContainText('No node selected');
    await page.getByTestId('fixture-catch-up').click();
    await expect(page.getByTestId('fixture-replay-cursor')).toHaveText('3/3');
    await expect(page.locator('[data-testid="runtime-node-card"][data-node-id="DEV-RUN-019"]')).toHaveAttribute('data-gate-state', 'PASSED');
    await page.getByTestId('hierarchy-select-DEV-RUN-019').click();
    await expect(page.getByTestId('inspector-node-id')).toHaveText('DEV-RUN-019');
    await expect(page.locator('[data-pane="overview"]')).toContainText('PASSED');
    await expect(page.getByRole('treeitem', { name: 'DEV-RUN-019, atomic', exact: true })).toHaveAttribute('aria-selected', 'true');
    await page.getByRole('button', { name: 'Collapse DEV-RUN-018', exact: true }).click();
    await expect(page.getByTestId('hierarchy-select-DEV-RUN-019')).toHaveCount(0);
    await page.getByRole('button', { name: 'Expand DEV-RUN-018', exact: true }).click();
    await page.getByTestId('runtime-fit').click();
    await page.getByTestId('unified-run-workspace').screenshot({ path: resolve(evidenceDir, 'shared-prefix-tree.png') });
    await page.getByTestId('player-first').click();
    await expect(page.getByTestId('fixture-replay-cursor')).toHaveText('0/3');
    await expect(page.getByTestId('node-inspector')).toContainText('No node selected');
    await expect(page.getByTestId('workspace-header')).toContainText('UNKNOWN');
    await expect(page.locator('[data-testid="runtime-node-card"][data-node-id="DEV-RUN-019"]')).toHaveAttribute('data-gate-state', 'UNKNOWN');
    await page.getByTestId('unified-run-workspace').screenshot({ path: resolve(evidenceDir, 'shared-prefix-empty.png') });
    await page.getByTestId('player-next').click();
    await expect(page.getByTestId('fixture-replay-cursor')).toHaveText('1/3');
    await page.getByTestId('fixture-mode-current').click();
    await expect(page.getByTestId('node-inspector')).toContainText('PASSED');
    await page.getByTestId('fixture-catalog').getByRole('button', { name: /DEV-RUN-022/ }).click();
    await expect(page.getByTestId('fixture-replay-cursor')).toHaveText('0/0');
    await page.getByTestId('fixture-event-arrive').click();
    await expect(page.getByTestId('fixture-replay-cursor')).toHaveText('1/1');
    await expect(page.locator('[data-pane="overview"]')).toContainText('WAITING');
    expect(errors).toEqual([]);
  });

  test("Run detail preserves G5 WAITING and DEV FIXTURE labeling", async ({ page }) => {
    await page.goto("/runs/DEV-RUN-022");
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("dev-fixture-indicator")).toContainText("DEV FIXTURE");
    const overview = page.locator("[data-pane='overview']");
    await expect(overview).toContainText(/G5/i);
    await expect(overview).toContainText(/WAITING/i);
    await page.screenshot({ path: resolve(evidenceDir, "dev-run-022-g5-waiting.png"), fullPage: true });
  });

  test("DEV-RUN-020 is incompatible and has no replay link", async ({ page }) => {
    await page.goto("/tasks/TASK-CORE/runs");
    await page.waitForLoadState("networkidle");
    const card = page.locator(".notion-run-card").filter({ hasText: "DEV-RUN-020" });
    await expect(card).toContainText("UNAVAILABLE");
    await expect(card).toContainText("DEGRADED");
    await expect(card.locator("a[href*='DEV-RUN-020']")).toHaveCount(0);
    await page.screenshot({ path: resolve(evidenceDir, "task-run-negative-020.png"), fullPage: true });
  });
});
