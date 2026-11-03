import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { materializeFixtureScenario } from "@/lib/dwo/materializeFixtureScenario";
import { classifyEvidenceSource } from "@/lib/dwo/evidenceClassification";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";

describe("R5 source-contract evidence classification", () => {
  it("retains receipt bytes as raw evidence without treating receipts as semantic histories", () => {
    const model = materializeFixtureScenario(FIXTURE_CATALOG.find((entry) => entry.id === "DEV-RUN-025")!);
    const node = model.nodes.find((entry) => entry.id === "DEV-RUN-025")!;
    const relativePath = "execution/DEV-RUN-025-execution.json";
    const source = readFileSync(join(process.cwd(), "dwo-v2/fixtures/DWO-UR-30-V1/evidence", relativePath), "utf8");

    expect(node.artifacts).toContain(relativePath);
    expect(node.runbook).toEqual([]);
    expect(node.taskControllerHistory).toEqual([]);
    expect(node.executorHistory).toEqual([]);
    expect(node.checkpoints).toEqual([]);
    expect(node.rawEvidence).toEqual(expect.arrayContaining([expect.objectContaining({ sourcePath: relativePath, content: source })]));
  });

  it("does not classify unsupported or absent contract source types by record fields", () => {
    expect(classifyEvidenceSource({ sourcePath: "closure/DEV-RUN-025-closure.json", content: "{}", record: { schema_id: "ClosureReceipt" } })).toEqual({ kind: "raw", reason: "NO_CANONICAL_SOURCE_CONTRACT" });
    expect(classifyEvidenceSource({ sourcePath: "runbook/anything.json", content: "{}", record: { record_id: "runbook" } })).toEqual({ kind: "raw", reason: "NO_CANONICAL_SOURCE_CONTRACT" });
  });
});
