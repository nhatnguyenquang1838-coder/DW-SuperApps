import { test, expect } from "@playwright/test";

// Navigation flows per TECH_SPEC §13.
//
// HONEST ASSERTIONS (rewritten after independent review)
// ------------------------------------------------------
// The previous version listed several selectors per flow and accepted "at
// least one exists". That made the assertion vacuous:
//
//   * one flow listed "h1" as a fallback, but the route renders an <h1>
//     unconditionally — so that fallback ALWAYS matched, including on a 404;
//   * the click was then wrapped in `if (await primary.count() > 0)`, so the
//     happy path (actually navigating and asserting the URL) was silently
//     skipped while the test still reported green.
//
// A test that cannot fail proves nothing. These flows now state exactly which
// state the product is in and assert that state positively, plus a negative
// assertion that catches fixture leakage into a production route.
//
// CURRENT TRUTH: the real task-relation source is NOT connected yet. /tasks and
// /tasks/[taskId]/runs therefore render their fail-closed UNAVAILABLE notices
// (lib/taskRead.ts reads the server source in real mode, never fixtures).
// These tests assert that fail-closed state explicitly.
// WHEN THE REAL SOURCE LANDS, the anchor-click + toHaveURL assertions must be
// restored — that is the point of writing them honestly now: the day the
// product changes, this test fails loudly instead of quietly staying green.

test.describe("DWO navigation — /tasks fail-closed contract", () => {
  test("/tasks renders the UNAVAILABLE notice and leaks no fixture data", async ({
    page,
  }) => {
    await page.goto("/tasks");
    await page.waitForLoadState("networkidle");

    // Positive: the fail-closed notice is present and visible.
    await expect(page.locator("text=Task source unavailable")).toBeVisible();

    // The notice must state the real source is missing — not present zeros.
    await expect(
      page.locator("text=real source not yet connected")
    ).toBeVisible();

    // Negative: no fixture-backed task rows may appear in real mode. A task
    // link here would mean a fixture reached a production route.
    await expect(page.locator('a[href^="/tasks/"]')).toHaveCount(0);
    await expect(page.locator("text=SCRUM-555")).toHaveCount(0);
  });

  test("/tasks/[taskId]/runs renders the no-relation notice, never a fallback run", async ({
    page,
  }) => {
    await page.goto("/tasks/SCRUM-555/runs");
    await page.waitForLoadState("networkidle");

    // The route 404s on an unknown task (fail-closed) or renders the explicit
    // "no relation record" notice. Both are correct fail-closed outcomes; what
    // must NEVER happen is a rendered run workspace.
    const emptyState = page.locator("text=No root runs resolved");
    const notFound = page.locator("text=404");

    if ((await emptyState.count()) > 0) {
      await expect(emptyState).toBeVisible();
    } else {
      // Unknown task -> Next notFound(). Assert a 404 page, not a page that
      // merely happened to render an <h1> and pass.
      await expect(notFound).toBeVisible();
      await expect(page.locator('a[href*="/runs/DW-OBS"]')).toHaveCount(0);
    }

    // No run workspace may be presented for a task with no relation record.
    await expect(page.locator('[data-testid="unified-workspace"]')).toHaveCount(0);
    await expect(page.locator("[data-node-id]")).toHaveCount(0);
  });
});

test.describe("DWO navigation — mode toggle", () => {
  test("replay → LIVE via the mode select", async ({ page }) => {
    await page.goto("/runs/DW-OBS-M5-20260823-MOCK?mode=replay&seq=5");
    await page.waitForLoadState("networkidle");

    // Single-anchor step: the control must exist, this path never degrades.
    const anchor = page.locator('[data-testid="workspace-mode-select"]').first();
    await expect(anchor).toHaveCount(1);

    await anchor.selectOption("LIVE");
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-mode="LIVE"]').first()).toBeVisible();
  });
});

test.describe("DWO navigation — fixture catalog", () => {
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
    const shell = page.locator(
      '[data-testid="unified-workspace"], .dwo-unified-workspace'
    );
    if ((await shell.count()) > 0) {
      await expect(shell.first().locator('[data-node-id]')).toHaveCount(0);
      await expect(
        shell.first().locator('[data-edge-id], .dwo-runtime-edge')
      ).toHaveCount(0);
    }
  });
});