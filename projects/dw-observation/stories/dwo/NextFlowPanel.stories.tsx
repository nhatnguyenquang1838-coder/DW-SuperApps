import type { Meta, StoryObj } from "@storybook/react";
import NextFlowPanel from "@/components/dwo/NextFlowPanel";
import { makeModel } from "./fixtures";

const meta: Meta<typeof NextFlowPanel> = {
  title: "DWO/NextFlowPanel",
  component: NextFlowPanel,
  tags: ["autodocs"],
};
export default meta;

type Story = StoryObj<typeof NextFlowPanel>;

export const resolved: Story = {
  args: { model: makeModel({ projectionStatus: "RESOLVED", status: "active", nodes: [{ id: "n1", gateId: "G0", title: "X", family: "f", nodeType: "t", authorityBoundary: "b", sourceStatus: "s", maturity: "m", declaredGates: [], purpose: null, fileReads: [], fileWrites: [], artifacts: [], runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [] }], edges: [], orderedSteps: [{ nodeId: "n1", sequence: 1 }], currentSequence: 1, canonicalHistoryAvailable: true, sourceDigest: null }) },
};
export const blocked: Story = {
  args: { model: makeModel({ projectionStatus: "BLOCKED", status: "blocked", nodes: [{ id: "n1", gateId: "G0", title: "X", family: "f", nodeType: "t", authorityBoundary: "b", sourceStatus: "s", maturity: "m", declaredGates: [], purpose: null, fileReads: [], fileWrites: [], artifacts: [], runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [] }], edges: [], orderedSteps: [{ nodeId: "n1", sequence: 1 }], currentSequence: 1, canonicalHistoryAvailable: true, sourceDigest: null }) },
};
export const unknown: Story = {
  args: { model: makeModel({ projectionStatus: "UNKNOWN", status: "unknown", nodes: [{ id: "n1", gateId: "G0", title: "X", family: "f", nodeType: "t", authorityBoundary: "b", sourceStatus: "s", maturity: "m", declaredGates: [], purpose: null, fileReads: [], fileWrites: [], artifacts: [], runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [] }], edges: [], orderedSteps: [{ nodeId: "n1", sequence: 1 }], currentSequence: 1, canonicalHistoryAvailable: true, sourceDigest: null }) },
};
export const conflict: Story = {
  args: { model: makeModel({ projectionStatus: "CONFLICT", status: "conflict", nodes: [{ id: "n1", gateId: "G0", title: "X", family: "f", nodeType: "t", authorityBoundary: "b", sourceStatus: "s", maturity: "m", declaredGates: [], purpose: null, fileReads: [], fileWrites: [], artifacts: [], runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [] }], edges: [], orderedSteps: [{ nodeId: "n1", sequence: 1 }], currentSequence: 1, canonicalHistoryAvailable: true, sourceDigest: null }) },
};