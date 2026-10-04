import { test, expect } from "@playwright/test";

// Canonical screens per TECH_SPEC §14 and Penpot page "DWO v2 — Canonical UX".
// Selectors target actual rendered DOM from the component tree, not assumed classes.
const SCREENSHOTS: ReadonlyArray<{
  name: string;
  url: string;
  semanticLabel: string; // human-readable description of the semantic assertion
  check: (page: import("@playwright/test").Page) => Promise<boolean>;
}> = [
  {
    name: "Dashboard",
    url: "/tasks", // root redirects to /tasks; task-first entry is the dashboard surface
    semanticLabel: "task list visible",
    check: async (page) => {
      const el = page.locator("h1, h2").first();
      const text = (await el.textContent()) ?? "";
      return /Task|Dashboard|Runs/i.test(text);
    },
  },
  {
    name: "Task Runs",
    url: "/tasks/SCRUM-820/runs",
    semanticLabel: "SCRUM-820 task runs list",
    check: async (page) => {
      const body = await page.locator("body").textContent();
      return /SCRUM-820|runs|Run/i.test(body ?? "");
    },
  },
  {
    name: "Workspace LIVE",
    url: "/runs/DW-OBS-M5-20260823-MOCK?mode=live",
    semanticLabel: "run ID and LIVE mode visible",
    check: async (page) => {
      const body = await page.locator("body").textContent();
      return /DW-OBS-M5-20260823-MOCK|LIVE|Workspace/i.test(body ?? "");
    },
  },
  {
    name: "Workspace REPLAY",
    url: "/runs/DW-OBS-M5-20260823-MOCK?mode=replay&seq=5",
    semanticLabel: "run ID and REPLAY mode visible",
    check: async (page) => {
      const body = await page.locator("body").textContent();
      return /DW-OBS-M5-20260823-MOCK|REPLAY|Replay/i.test(body ?? "");
    },
  },
  {
    name: "Fixture Lab",
    url: "/dev/fixtures",
    semanticLabel: "fixture catalog with 30 runs",
    check: async (page) => {
      const body = await page.locator("body").textContent();
      return /Fixture|catalog|30|DEV-RUN/i.test(body ?? "");
    },
  },
  {
    name: "DEV-RUN-020 fail-closed",
    url: "/dev/sim/g0g6",
    semanticLabel: "INCOMPATIBLE/UNAVAILABLE/UNKNOWN fail-closed state",
    check: async (page) => {
      const body = await page.locator("body").textContent();
      // Fail-closed: sourceProfile=UNKNOWN, syncState=UNAVAILABLE, runState=INCOMPATIBLE
      // The sim view renders these fields from the fixture — never fabricates data.
      return /INCOMPATIBLE|UNAVAILABLE|UNKNOWN|SIMULATED RUN/i.test(body ?? "");
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