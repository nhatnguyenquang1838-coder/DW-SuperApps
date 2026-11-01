import { expect, test } from "@playwright/test";

const runCard = (page: import("@playwright/test").Page, id: string) =>
  page.locator(".notion-run-card").filter({ hasText: id });

for (const [taskId, runIds] of [["TASK-CORE", ["DEV-RUN-001", "DEV-RUN-020"]], ["TASK-RESEARCH", ["DEV-RUN-024"]]] as const) {
  test(`R5 ${taskId} lifecycle, availability, and detail navigation`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    await page.goto(`/tasks/${taskId}/runs`);
    await expect(page.getByRole("heading", { name: taskId, exact: true })).toBeVisible();
    for (const runId of runIds) {
      const card = runCard(page, runId);
      await expect(card).toBeVisible();
      await expect(card.getByTestId(`view-details-${runId}`)).toHaveAttribute("href", `/runs/${runId}`);
      await expect(card.getByTestId(`axis-projection-sync-${runId}`)).toHaveAttribute("data-value", "GAP");
    }
    if (taskId === "TASK-CORE") {
      const incompatible = runCard(page, "DEV-RUN-020");
      await expect(incompatible.getByTestId("run-lifecycle-DEV-RUN-020")).toHaveText("INCOMPATIBLE");
      await expect(incompatible.getByTestId("replay-availability-DEV-RUN-020")).toHaveText("UNAVAILABLE");
      await expect(incompatible.getByRole("link", { name: /Open replay/i })).toHaveCount(0);
      await incompatible.getByRole("link", { name: /View details/i }).click();
      await expect(page).toHaveURL(/\/runs\/DEV-RUN-020$/);
      await expect(page.getByTestId("workspace-header")).toContainText("INCOMPATIBLE");
      await expect(page.getByTestId("runtime-node-card")).toHaveCount(0);
      await expect(page.getByTestId("player-play")).toBeDisabled();
    }
    expect(errors).toEqual([]);
  });
}

test("R5 replay CTA opens the actual replay route, distinct from run detail", async ({ page }) => {
  await page.goto("/tasks/TASK-RESEARCH/runs");
  const card = runCard(page, "DEV-RUN-024");
  await expect(card.getByRole("link", { name: /View details/i })).toHaveAttribute("href", "/runs/DEV-RUN-024");
  const replay = card.getByRole("link", { name: /Open replay/i });
  await expect(replay).toHaveAttribute("href", "/runs/DEV-RUN-024/replay");
  await replay.click();
  await expect(page).toHaveURL(/\/runs\/DEV-RUN-024\/replay$/);
  await expect(page.getByTestId("replay-pane")).toBeVisible();
});

test("R5 typed evidence tabs stay empty while raw/artifact bytes remain available", async ({ page }) => {
  await page.goto("/runs/DEV-RUN-025");
  const inspector = page.getByTestId("node-inspector");
  for (const [name, unavailable] of [["Runbook", /Runbook unavailable/], ["History", /history unavailable/], ["Checkpoints", /Checkpoints unavailable/]] as const) {
    await inspector.getByRole("button", { name, exact: true }).click();
    await expect(inspector.locator(".dwo-inspector-pane")).toContainText(unavailable);
    await expect(inspector.locator(".dwo-inspector-pane")).not.toContainText("ExecutionReceipt");
  }
  await inspector.getByRole("button", { name: "Raw", exact: true }).click();
  await expect(inspector.locator('[data-pane="raw"]')).toContainText("ExecutionReceipt");
  await inspector.getByRole("button", { name: "Artifacts", exact: true }).click();
  await expect(inspector.locator('[data-pane="artifacts"]')).toContainText("execution/DEV-RUN-025-execution.json");
});
