import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const evidenceDir = resolve(process.cwd(), "../../.preview-evidence/playwright-r1");
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
