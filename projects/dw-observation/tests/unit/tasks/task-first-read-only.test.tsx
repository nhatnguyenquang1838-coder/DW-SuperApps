import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import TasksPage from "../../../app/tasks/page";
import TaskRunsPage from "../../../app/tasks/[taskId]/runs/page";

describe("Task-first production routes are fixture-isolated", () => {
  it("does not import fixture relation records into /tasks", () => {
    const source = readFileSync(path.resolve(process.cwd(), "app/tasks/page.tsx"), "utf8");
    expect(source).not.toMatch(/taskFixtures|TASK_RELATION_RECORDS|TASK_META/);
  });

  it("renders an explicit unavailable state when no real task relation source is configured", async () => {
    const page = await TasksPage();
    render(page);
    expect(screen.getByText(/Task source unavailable/i)).toBeTruthy();
    expect(screen.queryByText("SCRUM-555")).toBeNull();
  });

  it("renders an unavailable Task→Run state instead of converting missing data to a 404", async () => {
    const page = await TaskRunsPage({ params: { taskId: "SCRUM-820" } });
    render(page);
    expect(screen.getByText(/Task relation unavailable/i)).toBeTruthy();
  });
});
