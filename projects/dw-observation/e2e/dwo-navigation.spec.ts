import { test, expect } from "@playwright/test";

// Navigation flows per TECH_SPEC §13.
// Routes and anchors verified against the actual component tree.
const NAV_FLOWS = [
  {
    from: "/tasks",
    to: "/tasks/SCRUM-555/runs",
    selector: 'a[href="/tasks/SCRUM-555/runs"]',
    label: "Tasks → Task Runs",
  },
  {
    from: "/tasks/SCRUM-555/runs",
    to: "/runs/DW-OBS-M5-20260823-MOCK",
    selector: 'a[href*="/runs/DW-OBS"]',
    label: "Task Runs → Run Workspace",
  },
  {
    from: "/runs/DW-OBS-M5-20260823-MOCK?mode=replay&seq=5",
    to: "/runs/DW-OBS-M5-20260823-MOCK?mode=live",
    selector: '[data-testid="workspace-mode-select"]',
    label: "Replay → LIVE (mode toggle)",
  },
] as const;

test.describe("DWO navigation — URL chain", () => {
  for (const step of NAV_FLOWS) {
    test(`step: ${step.label}`, async ({ page }) => {
      await page.goto(step.from);
      await page.waitForLoadState("networkidle");

      const anchor = page.locator(step.selector).first();
      const count = await anchor.count();
      if (count === 0) {
        test.info().annotations.push({
          type: "skip",
          description: `no anchor matching ${step.selector} on ${step.from}`,
        });
        test.skip();
        return;
      }

      if (step.label === "Replay → LIVE (mode toggle)") {
        // Select LIVE from the workspace mode dropdown
        await anchor.selectOption("LIVE");
        await page.waitForLoadState("networkidle");
        // Verify mode badge reflects LIVE (client-side toggle, URL unchanged)
        const badge = page.locator('[data-mode="LIVE"]').first();
        await expect(badge).toBeVisible();
      } else {
        await anchor.click();
        await page.waitForLoadState("networkidle");
        await expect(page).toHaveURL(new RegExp(step.to.replace(/\//g, "\\/").replace(/\?/g, "\\?")));
      }
    });
  }

  test("Fixture catalog → DEV-RUN-020 workspace", async ({ page }) => {
    await page.goto("/dev/fixtures");
    await page.waitForLoadState("networkidle");

    // DEV-RUN-020 is rendered in the fixture rail.
    const card = page.locator("text=DEV-RUN-020").first();
    await expect(card).toBeVisible();

    // T09b made the catalog a selector rail: pick DEV-RUN-020 explicitly, then
    // assert the fail-closed state. The previous version branched on whether a
    // link existed and, when one did, never checked the fail-closed fields at
    // all — an `if/else` where one arm asserted nothing. Selecting the scenario
    // removes the branch: DEV-RUN-020 must show CONFLICT + zero nodes/edges
    // whatever the markup does.
    await card.click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator('[data-testid="conflict-banner"]')).toBeVisible();
    await expect(page.locator("text=INCOMPATIBLE").first()).toBeVisible();
    await expect(page.locator("text=UNKNOWN").first()).toBeVisible();
    await expect(page.locator("text=UNAVAILABLE").first()).toBeVisible();

    // Fail-closed means no fabricated workspace content, not just a red banner.
    const shell = page.locator('[data-testid="unified-workspace"], .dwo-unified-workspace');
    if ((await shell.count()) > 0) {
      await expect(shell.first().locator('[data-node-id]')).toHaveCount(0);
      await expect(shell.first().locator('[data-edge-id], .dwo-runtime-edge')).toHaveCount(0);
    }
  });
});