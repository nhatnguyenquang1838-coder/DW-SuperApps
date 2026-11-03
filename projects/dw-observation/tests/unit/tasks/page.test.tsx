import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import TasksPage from "../../../app/tasks/page";

describe("TasksPage (/tasks) — fail-closed real-source entry", () => {
  it("shows source unavailability instead of fixture-backed tasks", async () => {
    const page = await TasksPage();
    render(page);

    expect(screen.getByText(/Task source unavailable/i)).toBeTruthy();
    expect(screen.queryByText("SCRUM-555")).toBeNull();
  });

  it("keeps the global Run Explorer link available", async () => {
    const page = await TasksPage();
    render(page);
    expect(screen.getByRole("link", { name: /Open Run Explorer/i }).getAttribute("href")).toBe("/runs");
  });
});

