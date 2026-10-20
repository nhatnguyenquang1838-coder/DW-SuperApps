import type { Meta, StoryObj } from "@storybook/react";
import RuntimeNodeCard from "@/components/dwo/RuntimeNodeCard";
import { makeNode } from "./fixtures";

/**
 * RuntimeNodeCard takes a single `data` prop, so `state` lives at `data.state`.
 * Declaring a top-level `state` argType is what previously forced the `as any`
 * casts (4 of them) and left 6 typecheck errors on this file. The component's
 * prop type now derives from `UnifiedRuntimeNode`, so the args are checked
 * against the real model instead of a hand-written copy that had drifted
 * (`boundary` vs the model's `authorityBoundary`).
 */
const meta: Meta<typeof RuntimeNodeCard> = {
  title: "DWO/RuntimeNodeCard",
  component: RuntimeNodeCard,
  tags: ["autodocs"],
  argTypes: {
    data: { control: "object" },
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
  args: { data: { ...baseData, node: makeNode({ id: "rn-1", title: "Done Node" }), state: "DONE" } },
};
export const active: Story = {
  args: { data: { ...baseData, state: "ACTIVE" } },
};
export const future: Story = {
  args: { data: { ...baseData, state: "FUTURE" } },
};
export const blocked: Story = {
  args: { data: { ...baseData, state: "BLOCKED" } },
};
export const unknown: Story = {
  args: { data: { ...baseData, state: "UNKNOWN" } },
};