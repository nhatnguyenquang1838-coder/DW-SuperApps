import type { Meta, StoryObj } from "@storybook/react";
import NodeInspector from "@/components/dwo/NodeInspector";
import { makeNode } from "./fixtures";

const meta: Meta<typeof NodeInspector> = {
  title: "DWO/NodeInspector",
  component: NodeInspector,
  tags: ["autodocs"],
  argTypes: {
    activeTab: {
      control: "select",
      options: ["overview", "files", "artifacts", "runbook", "history", "checkpoints", "raw"],
    },
  },
};
export default meta;

type Story = StoryObj<typeof NodeInspector>;

const baseNode = makeNode({
  id: "ni-1",
  title: "Inspector Node",
  family: "runtime",
  nodeType: "workflow",
  gateId: "G0_CONTEXT",
  authorityBoundary: "read_only",
  sourceStatus: "proposed",
  maturity: "experimental",
  declaredGates: ["G0_CONTEXT"],
  purpose: "Test purpose",
  fileReads: ["AGENTS.md", "workspace.yaml"],
  fileWrites: ["output.txt"],
  artifacts: [".gwc/tasks/TEST/artifact.json"],
  runbook: ["Step 1", "Step 2"],
  taskControllerHistory: [{ event_id: "tc-1", type: "node_admitted", actor: "TC", outcome: "accepted" }],
  executorHistory: [{ event_id: "ex-1", type: "executor_started", actor: "Hermes", outcome: "running" }],
  checkpoints: [{ checkpoint_id: "cp-1", revision: 1, status: "done" }],
});

export const overview: Story = { args: { node: baseNode, activeTab: "overview", onTabChange: () => {} } };
export const files: Story = { args: { node: baseNode, activeTab: "files", onTabChange: () => {} } };
export const artifacts: Story = { args: { node: baseNode, activeTab: "artifacts", onTabChange: () => {} } };
export const runbook: Story = { args: { node: baseNode, activeTab: "runbook", onTabChange: () => {} } };
export const history: Story = { args: { node: baseNode, activeTab: "history", onTabChange: () => {} } };
export const checkpoints: Story = { args: { node: baseNode, activeTab: "checkpoints", onTabChange: () => {} } };
export const raw: Story = { args: { node: baseNode, activeTab: "raw", onTabChange: () => {} } };