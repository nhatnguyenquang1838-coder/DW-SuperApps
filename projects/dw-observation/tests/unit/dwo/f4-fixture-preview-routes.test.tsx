/**
 * F4 — explicit local fixture mode wires the canonical Task-first and Run routes.
 * Production/default mode remains real/fail-closed (guarded by fixturePreviewMode).
 */
import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import TasksPage from "@/app/tasks/page";
import TaskRunsPage from "@/app/tasks/[taskId]/runs/page";
import RunDetailPage from "@/app/runs/[runId]/page";
import RunReplayPage from "@/app/runs/[runId]/replay/page";

const priorSource = process.env.OBSERVATORY_DATA_SOURCE;
afterEach(() => {
  if (priorSource === undefined) delete process.env.OBSERVATORY_DATA_SOURCE;
  else process.env.OBSERVATORY_DATA_SOURCE = priorSource;
});

function enableFixturePreview() {
  process.env.OBSERVATORY_DATA_SOURCE = "fixture";
}

describe("F4 local fixture preview canonical routes", () => {
  it("/tasks lists fixture relations with DEV FIXTURE badge and canonical Task links", async () => {
    enableFixturePreview();
    const { container } = render(await TasksPage());
    expect(screen.getByTestId("dev-fixture-indicator").textContent).toContain("DEV FIXTURE");
    expect(container.querySelectorAll(".notion-task-card")).toHaveLength(5);
    expect(container.querySelector("a[href='/tasks/TASK-CORE/runs']")).toBeTruthy();
  });

  it("/tasks/[taskId]/runs shows fixture root runs and links to canonical /runs detail", async () => {
    enableFixturePreview();
    const { container } = render(await TaskRunsPage({ params: { taskId: "TASK-CORE" } }));
    expect(screen.getByTestId("dev-fixture-indicator").textContent).toContain("DEV FIXTURE");
    expect(container.querySelectorAll(".notion-run-card")).toHaveLength(8);
    expect(container.querySelector("a[href='/runs/DEV-RUN-001']")).toBeTruthy();
    const negative = [...container.querySelectorAll(".notion-run-card")]
      .find((card) => card.textContent?.includes("DEV-RUN-020"));
    expect(negative?.querySelector("a[href*='DEV-RUN-020']")).toBeNull();
  });

  it("/runs/[runId] materializes fixture data, receipt axis, and canonical replay link", async () => {
    enableFixturePreview();
    const { container } = render(await RunDetailPage({
      params: { runId: "DEV-RUN-006" },
      searchParams: {},
    }));
    expect(screen.getByTestId("dev-fixture-indicator").textContent).toContain("DEV FIXTURE");
    expect(screen.getByTestId("unified-run-workspace")).toBeTruthy();
    expect(container.querySelector("a[href='/runs/DEV-RUN-006/replay']")).toBeTruthy();
    expect(container.querySelector("[data-testid='axis-qualification']")).toBeTruthy();
  });

  it("/runs/[runId]/replay uses fixture history while preserving the canonical URL", async () => {
    enableFixturePreview();
    const { container } = render(await RunReplayPage({ params: { runId: "DEV-RUN-001" } }));
    expect(screen.getByTestId("dev-fixture-indicator").textContent).toContain("DEV FIXTURE");
    expect(screen.getByTestId("replay-pane")).toBeTruthy();
    expect(screen.getByTestId("replay-sync").textContent).toBe("SYNCHRONIZED");
    expect(container.querySelector("a[href='/runs/DEV-RUN-001']")).toBeTruthy();
  });
});
