import { describe, expect, it } from "vitest";
import { render, within } from "@testing-library/react";
import DevTaskRunsPage from "@/app/dev/tasks/[taskId]/runs/page";
import { getFixtureTaskRelation } from "@/lib/dwo/fixtureTaskRead";
import { buildWorkspaceModel } from "@/lib/runtime/buildWorkspaceModel";

async function renderTask(taskId: string) {
  process.env.OBSERVATORY_DATA_SOURCE = "fixture";
  return render(await DevTaskRunsPage({ params: { taskId } }));
}

function runCard(runId: string) {
  return Array.from(document.querySelectorAll<HTMLElement>(".notion-run-card")).find((card) => card.textContent?.includes(runId)) ?? null;
}

describe("R5 task-run lifecycle and navigation", () => {
  it("renders canonical detail lifecycle for every related root independent of replay", async () => {
    const allRows: string[] = [];
    for (const taskId of ["TASK-CORE", "TASK-EVENT", "TASK-PARTY", "TASK-RESEARCH", "TASK-WEDDING"]) {
      const view = await renderTask(taskId);
      const relation = await getFixtureTaskRelation(taskId);
      expect(relation).not.toBeNull();
      for (const runId of relation!.rootRunIds) {
        allRows.push(runId);
        const card = runCard(runId);
        expect(card, runId).not.toBeNull();
        const { model: canonical } = await buildWorkspaceModel(runId, "fixture");
        expect(within(card!).getByRole("link", { name: "View details →" }).getAttribute("href")).toBe(`/runs/${runId}`);
        expect(within(card!).getByTestId(`run-lifecycle-${runId}`).textContent).toBe(canonical.status);
        expect(within(card!).getByTestId(`replay-availability-${runId}`).textContent).toBe(canonical.canonicalHistoryAvailable ? "AVAILABLE" : "UNAVAILABLE");
        expect(within(card!).getByTestId(`axis-projection-sync-${runId}`).getAttribute("data-value")).toBe(canonical.projectionSyncState);
        expect(within(card!).getByTestId("axis-qualification")).toBeTruthy();
        if (runId === "DEV-RUN-001") expect(within(card!).getByTestId(`run-lifecycle-${runId}`).textContent).toBe("OPEN");
        if (runId === "DEV-RUN-020") {
          expect(within(card!).getByTestId(`run-lifecycle-${runId}`).textContent).toBe("INCOMPATIBLE");
          expect(within(card!).getByTestId(`replay-availability-${runId}`).textContent).toBe("UNAVAILABLE");
        }
      }
      view.unmount();
    }
    expect(allRows.length).toBeGreaterThan(0);
    expect(new Set(allRows).size).toBe(allRows.length);

  });

  it("provides valid detail access even when incompatible replay is unavailable", async () => {
    await renderTask("TASK-CORE");
    const card = runCard("DEV-RUN-020")!;
    expect(within(card).getByRole("link", { name: "View details →" }).getAttribute("href")).toBe("/runs/DEV-RUN-020");
    expect(within(card).queryByRole("link", { name: /Open replay/i })).toBeNull();
    expect(within(card).getByTestId("replay-availability-DEV-RUN-020").textContent).toBe("UNAVAILABLE");
  });

  it("uses different destinations for detail and replay CTAs when canonical history exists", async () => {
    await renderTask("TASK-RESEARCH");
    const card = runCard("DEV-RUN-024")!;
    expect(within(card).getByRole("link", { name: "View details →" }).getAttribute("href")).toBe("/runs/DEV-RUN-024");
    expect(within(card).getByRole("link", { name: "Open replay →" }).getAttribute("href")).toBe("/runs/DEV-RUN-024/replay");
  });
});
