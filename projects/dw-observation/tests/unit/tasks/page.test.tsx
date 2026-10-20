import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import TasksPage from "@/app/tasks/page";

describe("TasksPage (/tasks) — primary product route (fixture-backed source)", () => {
  /**
   * P0 guard: the primary entry point must be source-backed. Per user
   * approval, fixture-backed seed records (TASK_RELATION_RECORDS) feed the
   * real adapter until an external connector wires the live source. SCRUM-555
   * has a relation record → must render as RESOLVED, NOT "Task source
   * unavailable" (which is fail-closed for a genuinely empty source).
   */
  it("renders source-backed task summaries when relation records exist", async () => {
    const html = await TasksPage();
    const { container } = render(html);

    expect(screen.queryByText("Task source unavailable")).toBeNull();
    expect(screen.getByText("SCRUM-555")).toBeTruthy();
    expect(screen.getByText("rev:1", { exact: false })).toBeTruthy();

    const card = container.querySelector(".notion-run-card");
    expect(card).toBeTruthy();
    expect(card?.textContent).toMatch(/1 run/);
  });

  it("does not surface a task with no relation record as resolved", async () => {
    // SCRUM-820 has no TASK_RELATION_RECORDS entry → must not appear as a
    // resolved card (fail-closed: no inference).
    const html = await TasksPage();
    render(html);
    expect(screen.queryByText("SCRUM-820")).toBeNull();
  });
});
