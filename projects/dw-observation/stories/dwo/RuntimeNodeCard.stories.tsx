import type { Meta, StoryObj } from "@storybook/react";
import RuntimeNodeCard from "@/components/dwo/RuntimeNodeCard";
import { makeNode, NODE_STATES } from "./fixtures";

const meta: Meta<typeof RuntimeNodeCard> = {
  title: "DWO/RuntimeNodeCard",
  component: RuntimeNodeCard,
  tags: ["autodocs"],
  argTypes: {
    state: {
      control: "select",
      options: ["DONE", "ACTIVE", "FUTURE", "BLOCKED", "UNKNOWN"],
    },
  },
};
export default meta;

type Story = StoryObj<typeof RuntimeNodeCard>;

const baseData = {
  node: makeNode({ id: "rn-1", title: "Runtime Node", family: "runtime", nodeType: "workflow" }),
  active: true,
  selected: false,
  boundary: "G0_CONTEXT",
  onOpen: () => {},
};

export const done: Story = {
  args: { data: { ...baseData, node: makeNode({ id: "rn-1", title: "Done Node" }), state: "DONE" as any } },
};
export const active: Story = {
  args: { data: { ...baseData, state: "ACTIVE" as any } },
};
export const future: Story = {
  args: { data: { ...baseData, state: "FUTURE" as any } },
};
export const blocked: Story = {
  args: { data: { ...baseData, state: "BLOCKED" as any } },
};
export const unknown: Story = {
  args: { data: { ...baseData, state: "UNKNOWN" as any } },
};