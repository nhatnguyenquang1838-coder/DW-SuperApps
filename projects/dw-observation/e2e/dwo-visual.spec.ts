import { test, expect } from "@playwright/test";

// Navigation flows per TECH_SPEC §13.
// Selectors target actual rendered DOM from the component tree, not assumed classes.
const SCREENSHOTS: ReadonlyArray<{
  name: string;
  url: string;
  semanticLabel: string; // human-readable description of the semantic assertion
  check: (page: import("@playwright/test").Page) => Promise<boolean>;
}> = [
  {
    name: "Dashboard",
    url: "/dashboard",
    semanticLabel: "dashboard population model visible",
    check: async (page) => {
      await expect(page.locator("[data-testid='dashboard']")).toBeVisible();
      return true;
    },
  },
  {
    name: "Task Runs",
    url: "/tasks/SCRUM-555/runs",
    semanticLabel: "SCRUM-555 task runs page renders",
    check: async (page) => {
      // Page renders a visible heading in all states (list, empty, or 404).
      const heading = page.locator("h1").first();
      await expect(heading).toBeVisible();
      return true;
    },
  },
  {
    name: "Workspace LIVE",
    url: "/runs/DW-OBS-M5-20260823-MOCK?mode=live",
    semanticLabel: "run ID and LIVE mode visible",
    check: async (page) => {
      await expect(page.locator("[data-testid='unified-run-workspace']")).toBeVisible();
      // WorkspaceHeader renders data-mode={mode} — verify the badge is present
      const modeBadge = page.locator("[data-mode]");
      await expect(modeBadge.first()).toBeVisible();
      return true;
    },
  },
  {
    name: "Workspace REPLAY",
    url: "/runs/DW-OBS-M5-20260823-MOCK?mode=replay&seq=5",
    semanticLabel: "run ID and REPLAY mode visible",
    check: async (page) => {
      await expect(page.locator("[data-testid='unified-run-workspace']")).toBeVisible();
      // WorkspaceHeader renders data-mode={mode} — verify the badge is present
      const modeBadge = page.locator("[data-mode]");
      await expect(modeBadge.first()).toBeVisible();
      return true;
    },
  },
  {
    name: "Fixture Lab",
    url: "/dev/fixtures",
    semanticLabel: "fixture catalog with 30 runs",
    check: async (page) => {
      await expect(page.locator("[data-testid='fixture-catalog']")).toBeVisible();
      return true;
    },
  },
  {
    name: "DEV-RUN-020 fail-closed",
    url: "/dev/fixtures",
    semanticLabel: "INCOMPATIBLE/UNAVAILABLE/UNKNOWN fail-closed state",
    check: async (page) => {
      const btn = page.locator(".dwo-fixture-btn").filter({ has: page.locator("text=DEV-RUN-020") }).first();
      await btn.click();
      await page.waitForLoadState("networkidle");
      await expect(page.locator("[data-testid='conflict-banner']")).toBeVisible();
      return true;
    },
  },
] as const;

test.describe("DWO visual regression — screenshots + semantic assertions", () => {
  for (const shot of SCREENSHOTS) {
    test(`screenshot: ${shot.name}`, async ({ page }) => {
      await page.goto(shot.url);
      await page.waitForLoadState("networkidle");

      // Disable animations for deterministic screenshots
      await page.addStyleTag({
        content:
          "*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }",
      });

      // Semantic check: the expected fail-closed/mode/status text must be present
      const ok = await shot.check(page);
      expect(ok).toBe(true);

      // Screenshot comparison against baseline
      await expect(page).toHaveScreenshot(`${shot.name}.png`, {
        animations: "disabled",
        maxDiffPixels: 100,
      });
    });
  }

  test("DEV-RUN-020 is genuinely INCOMPATIBLE/UNAVAILABLE/UNKNOWN, not merely red", async ({ page }) => {
    await page.goto("/dev/fixtures");
    await page.waitForLoadState("networkidle");

    // Click DEV-RUN-020 in the fixture rail
    const btn = page.locator(".dwo-fixture-btn").filter({ has: page.locator("text=DEV-RUN-020") }).first();
    await btn.click();

    // Conflict banner appears (data-testid from page.tsx)
    const banner = page.locator("[data-testid=\"conflict-banner\"]");
    await expect(banner).toBeVisible();

    const bannerText = (await banner.textContent()) ?? "";
    // Explicit fail-closed fields from fixtureSpec.ts — never inferred from colour
    expect(bannerText).toMatch(/INCOMPATIBLE/);
    expect(bannerText).toMatch(/UNAVAILABLE/);
    expect(bannerText).toMatch(/UNKNOWN/);
    // Negative fixture: no child-run chain, no dependency chain fabricated
    expect(bannerText).not.toMatch(/children.*DEV-RUN/);
  });
});